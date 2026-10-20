"""Shared base entity and device info."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FIRMWARE, CONF_MODEL, DEFAULT_MODEL, DOMAIN
from .coordinator import EversoloCoordinator


class EversoloEntity(CoordinatorEntity[EversoloCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Eversolo",
            model=entry.data.get(CONF_MODEL) or DEFAULT_MODEL,
            sw_version=entry.data.get(CONF_FIRMWARE),
            configuration_url=coordinator.api.base,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
