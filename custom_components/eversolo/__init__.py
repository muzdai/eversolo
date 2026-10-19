"""Eversolo integration: media player, selects and switch for Eversolo DMP/DAC devices."""
from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EversoloApi, EversoloError
from .const import CARD_URL, CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN, VERSION
from .coordinator import EversoloCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SELECT, Platform.SWITCH]

SERVICE_SET_INPUT = "set_input"
SERVICE_SET_OUTPUT = "set_output"
SERVICE_SET_SERVICE = "set_service"
SERVICE_SET_VU_MODE = "set_vu_mode"
SERVICE_SET_DISPLAY = "set_display"
SERVICE_SET_LOOP_MODE = "set_loop_mode"
SERVICE_REQUEST = "request"

ATTR_ENTITY_ID = "entity_id"
ATTR_NAME = "name"

_ENTITY_SCHEMA = {vol.Required(ATTR_ENTITY_ID): cv.entity_id}
SCHEMA_NAME = vol.Schema({**_ENTITY_SCHEMA, vol.Required(ATTR_NAME): cv.string})
SCHEMA_VU = vol.Schema({**_ENTITY_SCHEMA, vol.Required("mode"): vol.In(["vu", "spectrum"])})
SCHEMA_DISPLAY = vol.Schema({**_ENTITY_SCHEMA, vol.Required("on"): cv.boolean})
SCHEMA_LOOP = vol.Schema({**_ENTITY_SCHEMA, vol.Required("mode"): vol.In(["list", "single", "shuffle"])})
SCHEMA_REQUEST = vol.Schema(
    {
        **_ENTITY_SCHEMA,
        vol.Required("path"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = EversoloApi(session, entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = EversoloCoordinator(hass, api, entry.title)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await _async_register_card(hass)
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
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and load it on every dashboard (once per HA run)."""
    flag = f"{DOMAIN}_card_registered"
    if hass.data.get(flag):
        return
    hass.data[flag] = True
    path = os.path.join(os.path.dirname(__file__), "www", "eversolo-player-card.js")
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, path, False)])
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> EversoloCoordinator:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.config_entry_id not in hass.data.get(DOMAIN, {}):
        raise HomeAssistantError(f"{entity_id} is not an Eversolo entity")
    return hass.data[DOMAIN][entry.config_entry_id]


def _resolve(items: list[dict], wanted: str) -> dict:
    for item in items:
        if item["name"] == wanted or item["tag"] == wanted:
            return item
    raise HomeAssistantError(f"'{wanted}' is not available on the device")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_INPUT):
        return

    async def set_input(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        item = _resolve(coord.io["inputs"], call.data[ATTR_NAME])
        await coord.api.set_input(item["tag"])
        await coord.async_request_refresh()

    async def set_output(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        item = _resolve(coord.io["outputs"], call.data[ATTR_NAME])
        await coord.api.set_output(item["tag"])
        await coord.async_request_refresh()

    async def set_service(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        item = _resolve(coord.services, call.data[ATTR_NAME])
        await coord.api.set_service(item["tag"])
        await coord.async_request_refresh()

    async def set_vu_mode(call: ServiceCall) -> None:
        from .const import VU_OPEN_TYPE

        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        await coord.api.set_vu(VU_OPEN_TYPE[call.data["mode"]])
        await coord.async_request_refresh()

    async def set_display(call: ServiceCall) -> None:
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        on = call.data["on"]
        await coord.api.set_display(on)
        coord.display_on = on
        coord.async_update_listeners()

    async def set_loop_mode(call: ServiceCall) -> None:
        from .const import LOOP_LIST, LOOP_SHUFFLE, LOOP_SINGLE

        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        mode = {"list": LOOP_LIST, "single": LOOP_SINGLE, "shuffle": LOOP_SHUFFLE}[call.data["mode"]]
        await coord.api.set_loop(mode)
        await coord.async_request_refresh()

    async def request(call: ServiceCall) -> ServiceResponse:
        """Raw GET to the device, for probing unverified endpoints."""
        coord = _coordinator_for(hass, call.data[ATTR_ENTITY_ID])
        path = call.data["path"]
        if not path.startswith("/"):
            raise HomeAssistantError("path must start with /")
        try:
            result = await coord.api.request(path, raw=True)
        except EversoloError as err:
            raise HomeAssistantError(str(err)) from err
        return {"response": result}

    hass.services.async_register(DOMAIN, SERVICE_SET_INPUT, set_input, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, SERVICE_SET_OUTPUT, set_output, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, SERVICE_SET_SERVICE, set_service, SCHEMA_NAME)
    hass.services.async_register(DOMAIN, SERVICE_SET_VU_MODE, set_vu_mode, SCHEMA_VU)
    hass.services.async_register(DOMAIN, SERVICE_SET_DISPLAY, set_display, SCHEMA_DISPLAY)
    hass.services.async_register(DOMAIN, SERVICE_SET_LOOP_MODE, set_loop_mode, SCHEMA_LOOP)
    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST, request, SCHEMA_REQUEST, supports_response=SupportsResponse.ONLY
    )
