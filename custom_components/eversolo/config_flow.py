"""Config flow: pair with the device (confirm on its screen) and create the entry."""
from __future__ import annotations

import ipaddress
import uuid
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import EversoloApi, EversoloError
from .wol import normalize_mac
from .const import (
    CLIENT_NAME,
    CONF_BROADCAST,
    CONF_CLIENT_UUID,
    CONF_FIRMWARE,
    CONF_HOST,
    CONF_MAC,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


class EversoloConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Home Assistant looks this up as a static method on the flow handler."""
        return EversoloOptionsFlow()

    def __init__(self) -> None:
        self._name: str = DEFAULT_NAME
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._model: str | None = None
        self._mac: str | None = None
        self._client_uuid: str = str(uuid.uuid4())

    def _api(self) -> EversoloApi:
        return EversoloApi(async_get_clientsession(self.hass), self._host, self._port)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        # TXT records carry what the app reads in DiscoverManager: name is the model
        # (e.g. DMP-A6), deviceName the name set on the device, uuid / net_mac its ids.
        props = {k: v for k, v in (discovery_info.properties or {}).items() if isinstance(v, str)}
        self._host = discovery_info.host
        self._port = int(props.get("port") or discovery_info.port or DEFAULT_PORT)
        self._model = props.get("name") or None
        self._mac = normalize_mac(props.get("net_mac"))
        self._name = props.get("deviceName") or self._model or DEFAULT_NAME
        # Already added (manually or earlier): match by address as well as by id.
        self._async_abort_entries_match({CONF_HOST: self._host})
        await self.async_set_unique_id(props.get("uuid") or discovery_info.host)
        updates = {CONF_HOST: self._host, CONF_PORT: self._port}
        if self._mac:
            updates[CONF_MAC] = self._mac
        self._abort_if_unique_id_configured(updates=updates)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip() or DEFAULT_NAME
            self._host = user_input[CONF_HOST].strip()
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                resp = await self._api().connect(CLIENT_NAME, self._client_uuid, ask_authority=False)
            except EversoloError:
                errors["base"] = "cannot_connect"
            else:
                if resp.get("status") == 200:
                    return await self._async_finish(resp)
                if resp.get("status") == -2:
                    # The device shows its own prompt now and waits for an answer.
                    return await self._async_request_authority()
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self._name): str,
                vol.Required(CONF_HOST, default=self._host): str,
                vol.Optional(CONF_PORT, default=self._port): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _async_request_authority(self) -> ConfigFlowResult:
        """Send tag=1 right away; it blocks until the user answers on the device or it times out."""
        try:
            resp = await self._api().connect(CLIENT_NAME, self._client_uuid, ask_authority=True)
        except EversoloError:
            errors = {"base": "cannot_connect"}
        else:
            if resp.get("status") == 200:
                return await self._async_finish(resp)
            errors = {"base": "not_authorized"}
        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def async_step_authorize(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # Retry after a timeout or refusal: ask the device again.
        return await self._async_request_authority()

    async def _async_finish(self, resp: dict) -> ConfigFlowResult:
        device = resp.get("device") if isinstance(resp.get("device"), dict) else {}
        duuid = resp.get("duuid") or device.get("uuid") or resp.get("net_mac") or self._host
        model = self._model or device.get("name") or resp.get("model")
        await self.async_set_unique_id(str(duuid), raise_on_progress=False)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
        return self.async_create_entry(
            title=self._name,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_CLIENT_UUID: self._client_uuid,
                CONF_FIRMWARE: resp.get("firmware"),
                CONF_MODEL: model,
                CONF_MAC: normalize_mac(resp.get("net_mac")) or self._mac,
            },
        )


class EversoloOptionsFlow(OptionsFlow):
    """Change name, host or port. The entry is reloaded after saving."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip() or DEFAULT_NAME
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            mac_text = (user_input.get(CONF_MAC) or "").strip()
            mac = normalize_mac(mac_text)
            broadcast = (user_input.get(CONF_BROADCAST) or "").strip() or None
            if mac_text and not mac:
                errors[CONF_MAC] = "invalid_mac"
            elif broadcast and not _is_ipv4(broadcast):
                errors[CONF_BROADCAST] = "invalid_broadcast"
            elif (host, port) != (entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)):
                # Only a new address needs the player online (and paired) to check it.
                api = EversoloApi(async_get_clientsession(self.hass), host, port)
                try:
                    resp = await api.connect(CLIENT_NAME, entry.data[CONF_CLIENT_UUID], ask_authority=False)
                except EversoloError:
                    errors["base"] = "cannot_connect"
                else:
                    if resp.get("status") != 200:
                        errors["base"] = "not_authorized"
                    mac = mac or normalize_mac(resp.get("net_mac"))
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=name,
                    data={**entry.data, CONF_HOST: host, CONF_PORT: port, CONF_MAC: mac, CONF_BROADCAST: broadcast},
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=entry.title): str,
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Optional(CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_MAC, description={"suggested_value": entry.data.get(CONF_MAC)}): str,
                vol.Optional(CONF_BROADCAST, description={"suggested_value": entry.data.get(CONF_BROADCAST)}): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


def _is_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False
