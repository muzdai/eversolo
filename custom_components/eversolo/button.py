"""Buttons: VU / spectrum display mode and the device's own power menu."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [
        EversoloDisplayButton(coordinator, entry, "vu"),
        EversoloDisplayButton(coordinator, entry, "spectrum"),
    ]
    # One button per entry of the device's power menu (standby, screen off, reboot, ...).
    # Names come from the device in its UI language.
    entities += [EversoloPowerButton(coordinator, entry, opt) for opt in coordinator.power_options]
    async_add_entities(entities)


class EversoloDisplayButton(EversoloEntity, ButtonEntity):
    """Same as the app's VU / spectrum button: each press moves to the next mode."""

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, kind: str) -> None:
        super().__init__(coordinator, entry, f"{kind}_next")
        self._attr_translation_key = kind
        self._kind = kind

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self.coordinator.data or {}
        # The app hides the VU button below -1 and the spectrum button below 0.
        # Missing fields fall back to MusicState's defaults (vuDisplayMode 0, spDisplayMode -1).
        if self._kind == "vu":
            return data.get("vuDisplayMode", 0) >= -1
        return data.get("spDisplayMode", -1) >= 0

    async def async_press(self) -> None:
        if self._kind == "vu":
            await self.coordinator.api.vu_next()
        else:
            await self.coordinator.api.spectrum_next()
        self.coordinator.confirm_later()


class EversoloPowerButton(EversoloEntity, ButtonEntity):
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, option: dict) -> None:
        super().__init__(coordinator, entry, f"power_{option['tag']}")
        self._attr_name = option["name"]
        self._tag = option["tag"]

    async def async_press(self) -> None:
        await self.coordinator.api.power(self._tag)
