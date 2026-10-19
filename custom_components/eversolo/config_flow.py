"""Config flow: pair with the device (confirm on its screen) and create the entry."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EversoloApi, EversoloError
from .const import (
    CLIENT_NAME,
    CONF_CLIENT_UUID,
    CONF_FIRMWARE,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    return EversoloOptionsFlow()


class EversoloConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._name: str = DEFAULT_NAME
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._client_uuid: str = str(uuid.uuid4())

    def _api(self, host: str, port: int) -> EversoloApi:
        return EversoloApi(async_get_clientsession(self.hass), host, port)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        self._host = discovery_info.host
        await self.async_set_unique_id(discovery_info.host)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.name.split(".")[0]}
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._name = user_input[CONF_NAME].strip() or DEFAULT_NAME
            self._host = user_input[CONF_HOST].strip()
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                resp = await self._api(self._host, self._port).connect(
                    CLIENT_NAME, self._client_uuid, ask_authority=False
                )
            except EversoloError:
                errors["base"] = "cannot_connect"
            else:
                if resp.get("status") == 200:
                    return await self._async_finish(resp)
                if resp.get("status") == -2:
                    return await self.async_step_authorize()
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self._name): str,
                vol.Required(CONF_HOST, default=self._host): str,
                vol.Optional(CONF_PORT, default=self._port): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_authorize(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                resp = await self._api(self._host, self._port).connect(
                    CLIENT_NAME, self._client_uuid, ask_authority=True
                )
            except EversoloError:
                errors["base"] = "cannot_connect"
            else:
                if resp.get("status") == 200:
                    return await self._async_finish(resp)
                errors["base"] = "not_authorized"
        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"host": self._host},
        )

    async def _async_finish(self, resp: dict) -> ConfigFlowResult:
        device = resp.get("device") if isinstance(resp.get("device"), dict) else {}
        duuid = resp.get("duuid") or device.get("duuid") or resp.get("net_mac") or self._host
        await self.async_set_unique_id(str(duuid))
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
        return self.async_create_entry(
            title=self._name,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_CLIENT_UUID: self._client_uuid,
                CONF_FIRMWARE: resp.get("firmware"),
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
            api = EversoloApi(async_get_clientsession(self.hass), host, port)
            try:
                resp = await api.connect(CLIENT_NAME, entry.data[CONF_CLIENT_UUID], ask_authority=False)
            except EversoloError:
                errors["base"] = "cannot_connect"
            else:
                if resp.get("status") != 200:
                    errors["base"] = "not_authorized"
                else:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        title=name,
                        data={**entry.data, CONF_HOST: host, CONF_PORT: port},
                    )
                    return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=entry.title): str,
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Optional(CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
