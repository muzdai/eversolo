"""Eversolo Home Assistant integration."""

from __future__ import annotations

import shutil
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EversoloCoordinator

PLATFORMS = [Platform.MEDIA_PLAYER]


def _install_frontend_card(hass: HomeAssistant) -> None:
    """Copy the bundled Lovelace card into Home Assistant's /config/www directory."""
    source = Path(__file__).parent / "www" / "eversolo-player-card.js"
    destination = Path(hass.config.path("www", "eversolo-player-card.js"))

    if not source.is_file():
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or source.read_bytes() != destination.read_bytes():
        shutil.copy2(source, destination)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.async_add_executor_job(_install_frontend_card, hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Also refresh the card when the integration is reloaded or updated.
    await hass.async_add_executor_job(_install_frontend_card, hass)

    coordinator = EversoloCoordinator(hass, entry.data["host"], entry.data["port"])
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
