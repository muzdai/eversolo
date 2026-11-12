"""Diagnostics download: what the player reports, for bug reports (Settings > Devices > Eversolo)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_UUID, CONF_MAC, DOMAIN

TO_REDACT_ENTRY = {CONF_CLIENT_UUID, CONF_MAC, "unique_id"}
# Account names and ids of streaming services may appear in the player state.
TO_REDACT_STATE = {"userName", "userId", "token", "account", "email", "mac", "net_mac", "uuid", "duuid", "sn"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    result: dict[str, Any] = {
        "entry": async_redact_data({"title": entry.title, "unique_id": entry.unique_id, **entry.data}, TO_REDACT_ENTRY),
    }
    if coordinator is None:
        return result
    mirror = getattr(coordinator, "mirror", None)
    result.update(
        {
            "online": coordinator.last_update_success,
            "polling_seconds": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "state": async_redact_data(coordinator.data or {}, TO_REDACT_STATE),
            "inputs_outputs": coordinator.io,
            "power_options": coordinator.power_options,
            "apps": coordinator.apps,
            "brightness": coordinator.brightness,
            "dsp": coordinator.dsp,
            "mirror": {
                "running": bool(mirror and mirror.port is not None),
                "width": getattr(mirror, "width", None),
                "height": getattr(mirror, "height", None),
                "viewers": len(getattr(mirror, "_viewers", {})),
            },
        }
    )
    return result
