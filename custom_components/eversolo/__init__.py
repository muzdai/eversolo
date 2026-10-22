"""Eversolo integration: media player, selects and buttons for Eversolo DMP/DAC devices."""
from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EversoloApi, EversoloError
from .const import CARD_URL, CONF_HOST, ICONS_URL, CONF_PORT, DEFAULT_PORT, DOMAIN, LOOP_MODES, VERSION
from .coordinator import EversoloCoordinator
from .mirror import MirrorSession

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SELECT, Platform.BUTTON]

ATTR_ENTITY_ID = "entity_id"
ATTR_NAME = "name"

_ENTITY_SCHEMA = {vol.Required(ATTR_ENTITY_ID): cv.entity_id}
SCHEMA_ENTITY = vol.Schema(_ENTITY_SCHEMA)
SCHEMA_NAME = vol.Schema({**_ENTITY_SCHEMA, vol.Required(ATTR_NAME): cv.string})
SCHEMA_LOOP = vol.Schema({**_ENTITY_SCHEMA, vol.Required("mode"): vol.In(list(LOOP_MODES))})
SCHEMA_REQUEST = vol.Schema({**_ENTITY_SCHEMA, vol.Required("path"): cv.string})


MIRROR_KEYS = ["Back", "Home", "Info", "VolumeUp", "VolumeDown", "Mute"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    websocket_api.async_register_command(hass, ws_mirror_subscribe)
    websocket_api.async_register_command(hass, ws_mirror_touch)
    websocket_api.async_register_command(hass, ws_mirror_key)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Before talking to the player: the cards (and icons) must load even while it is off,
    # otherwise dashboards show "Custom element doesn't exist" during setup retries.
    await _async_register_card(hass)
    session = async_get_clientsession(hass)
    api = EversoloApi(session, entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = EversoloCoordinator(hass, api, entry.title)
    await coordinator.async_config_entry_first_refresh()
    coordinator.mirror = MirrorSession(hass, api)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _async_register_services(hass)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after the options flow changed name, host or port."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None and getattr(coordinator, "mirror", None):
            await coordinator.mirror.async_shutdown()
    return unloaded


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and the eversolo:* icon set (once per HA run).

    The card goes in as a dashboard resource: dashboards wait for their resources
    before creating cards, while extra modules load in parallel and can lose that
    race (a panel view then keeps "Custom element doesn't exist"). The icon set
    stays an extra module so eversolo:* icons work on every page.
    """
    flag = f"{DOMAIN}_card_registered"
    if hass.data.get(flag):
        return
    hass.data[flag] = True
    www = os.path.join(os.path.dirname(__file__), "www")
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(CARD_URL, os.path.join(www, "eversolo-player-card.js"), False),
            StaticPathConfig(ICONS_URL, os.path.join(www, "eversolo-icons.js"), False),
        ]
    )
    frontend.add_extra_js_url(hass, f"{ICONS_URL}?v={VERSION}")
    if not await _async_register_card_resource(hass):
        frontend.add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")


async def _async_register_card_resource(hass: HomeAssistant) -> bool:
    """Add or update the card's dashboard resource. False when resources are YAML-managed."""
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None or not hasattr(resources, "async_create_item"):
        return False
    try:
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        url = f"{CARD_URL}?v={VERSION}"
        found = False
        for item in list(resources.async_items()):
            item_url = str(item.get("url", ""))
            if not item_url.split("?")[0].endswith("/eversolo-player-card.js"):
                continue
            if item_url.split("?")[0] == CARD_URL and not found:
                found = True
                if item_url != url or item.get("type") != "module":
                    await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            else:
                # Older copies of this card (e.g. /local/eversolo-player-card.js) would load a stale version.
                await resources.async_delete_item(item["id"])
        if not found:
            await resources.async_create_item({"res_type": "module", "url": url})
    except Exception as err:  # noqa: BLE001 - never block setup on the frontend helper
        _LOGGER.warning("Could not register the Eversolo card as a dashboard resource: %s", err)
        return False
    return True


class EversoloOffline(HomeAssistantError):
    """The entity is ours, but its config entry is not loaded (player off or unreachable)."""


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> EversoloCoordinator:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or getattr(entry, "platform", DOMAIN) != DOMAIN:
        raise HomeAssistantError(f"{entity_id} is not an Eversolo entity")
    coordinator = hass.data.get(DOMAIN, {}).get(entry.config_entry_id)
    if coordinator is None:
        # Setup is retried while the player is off, so the entry exists but is not loaded yet.
        raise EversoloOffline(f"{entity_id}: device offline")
    return coordinator


def _resolve(items: list[dict], wanted: str, *keys: str) -> dict:
    for item in items:
        if any(item.get(k) == wanted for k in ("name", *keys)):
            return item
    raise HomeAssistantError(f"'{wanted}' is not available on the device")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "set_input"):
        return

    async def set_input(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        item = _resolve(coord.io["inputs"], call.data[ATTR_NAME], "tag")
        await coord.api.set_input(item["tag"], item["index"])
        coord.select_io("inputs", item["index"])

    async def set_output(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        item = _resolve(coord.io["outputs"], call.data[ATTR_NAME], "tag")
        await coord.api.set_output(item["tag"], item["index"])
        coord.select_io("outputs", item["index"])

    async def set_loop_mode(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        await coord.api.set_loop(LOOP_MODES[call.data["mode"]])
        coord.apply(state={"loopModel": LOOP_MODES[call.data["mode"]]})

    async def vu_next(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        await coord.api.vu_next()
        coord.confirm_later()

    async def spectrum_next(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        await coord.api.spectrum_next()
        coord.confirm_later()

    async def open_app(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        app = _resolve(coord.apps, call.data[ATTR_NAME], "package")
        await coord.api.open_app(app["package"])
        coord.last_app = app["name"]
        coord.async_update_listeners()

    async def power(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        option = _resolve(coord.power_options, call.data[ATTR_NAME], "tag")
        await coord.api.power(option["tag"])

    async def request(call: ServiceCall) -> ServiceResponse:
        """Raw GET to the device, for probing endpoints."""
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        path = call.data["path"]
        if not path.startswith("/"):
            raise HomeAssistantError("path must start with /")
        try:
            result = await coord.api.request(path, raw=True)
        except EversoloError as err:
            raise HomeAssistantError(str(err)) from err
        return {"response": result}

    hass.services.async_register(DOMAIN, "set_input", set_input, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, "set_output", set_output, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, "set_loop_mode", set_loop_mode, SCHEMA_LOOP)
    hass.services.async_register(DOMAIN, "vu_next", vu_next, SCHEMA_ENTITY)
    hass.services.async_register(DOMAIN, "spectrum_next", spectrum_next, SCHEMA_ENTITY)
    hass.services.async_register(DOMAIN, "open_app", open_app, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, "power", power, SCHEMA_NAME)
    hass.services.async_register(
        DOMAIN, "request", request, SCHEMA_REQUEST, supports_response=SupportsResponse.ONLY
    )


# ---- screen mirroring over the HA websocket ---------------------------------
@websocket_api.websocket_command(
    {vol.Required("type"): "eversolo/mirror/subscribe", vol.Required("entity_id"): cv.entity_id}
)
@websocket_api.async_response
async def ws_mirror_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Stream the device screen to the card: config (SPS/PPS) and H.264 frames, base64."""
    try:
        coord = _coordinator_for(hass, msg["entity_id"])
    except EversoloOffline as err:
        connection.send_error(msg["id"], "device_offline", str(err))
        return
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    msg_id = msg["id"]

    @callback
    def forward(payload: dict) -> None:
        connection.send_message(websocket_api.event_message(msg_id, payload))

    try:
        unsubscribe = await coord.mirror.async_subscribe(forward)
    except (EversoloError, OSError, TimeoutError) as err:
        _LOGGER.debug("Screen mirroring could not start: %s", err)
        connection.send_error(msg_id, "device_offline", str(err))
        return
    connection.subscriptions[msg_id] = unsubscribe
    connection.send_result(msg_id)
    coord.mirror.replay(forward)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eversolo/mirror/touch",
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("action"): vol.In([0, 1, 2]),
        vol.Required("x"): vol.Coerce(int),
        vol.Required("y"): vol.Coerce(int),
    }
)
@websocket_api.async_response
async def ws_mirror_touch(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Touch on the mirrored screen: action 0 down, 2 move, 1 up; x/y in video pixels."""
    try:
        coord = _coordinator_for(hass, msg["entity_id"])
        await coord.mirror.async_touch(msg["action"], msg["x"], msg["y"])
    except (HomeAssistantError, OSError) as err:
        connection.send_error(msg["id"], "touch_failed", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eversolo/mirror/key",
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("key"): vol.In(MIRROR_KEYS),
    }
)
@websocket_api.async_response
async def ws_mirror_key(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Navigation keys of the app's remote screen (Home, Back, volume)."""
    try:
        coord = _coordinator_for(hass, msg["entity_id"])
        await coord.api.key(msg["key"])
    except (HomeAssistantError, EversoloError) as err:
        connection.send_error(msg["id"], "key_failed", str(err))
        return
    connection.send_result(msg["id"])
