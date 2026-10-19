"""Front-panel display on/off switch (experimental, see README)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloDisplaySwitch(coordinator, entry)])


class EversoloDisplaySwitch(EversoloEntity, SwitchEntity):
    _attr_name = "Front display"
    _attr_translation_key = "display"

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "display")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.display_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.api.set_display(True)
        self.coordinator.display_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.set_display(False)
        self.coordinator.display_on = False
        self.async_write_ha_state()
