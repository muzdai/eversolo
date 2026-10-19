"""Shared base entity and device info."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FIRMWARE, DOMAIN
from .coordinator import EversoloCoordinator


class EversoloEntity(CoordinatorEntity[EversoloCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            # Fixed device name keeps entity ids universal: media_player.eversolo,
            # select.eversolo_input, switch.eversolo_front_display, ...
            # A second device gets the automatic suffix (eversolo_2).
            name="Eversolo",
            manufacturer="Eversolo",
            model=entry.title,
            sw_version=entry.data.get(CONF_FIRMWARE),
            configuration_url=coordinator.api.base,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
