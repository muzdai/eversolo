"""Power switch: on = Wake on LAN, off = the device's own power-off command (see power.py)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPowerSwitch(coordinator, entry)])


class EversoloPowerSwitch(EversoloEntity, SwitchEntity):
    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "power")

    @property
    def available(self) -> bool:
        # Must stay usable while the player is off, as long as we know where to send the packet.
        return self.coordinator.last_update_success or self.coordinator.power.can_wake

    @property
    def is_on(self) -> bool:
        return self.coordinator.power.is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mac": self.coordinator.power.mac}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.power.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.power.async_turn_off()
