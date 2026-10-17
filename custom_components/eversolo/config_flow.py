"""Config flow for Eversolo."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import EversoloApiError, EversoloClient

class EversoloConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input["port"]
            try:
                client = EversoloClient(self.hass, host, port)
                model = await client.async_get_model()
            except EversoloApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=model or f"Eversolo ({host})",
                    data={"host": host, "port": port, "name": model or "Eversolo"},
                )
        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional("port", default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)