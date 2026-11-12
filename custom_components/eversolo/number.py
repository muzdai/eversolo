"""Numbers: display and knob brightness (only what the model has)."""
from __future__ import annotations

import asyncio

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BRIGHTNESS_KINDS, DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    added: set[str] = set()

    @callback
    def _add() -> None:
        # Read from the player once it answers, so the entities show up when the settings do.
        new = [kind for kind in coordinator.brightness if kind in BRIGHTNESS_KINDS and kind not in added]
        if new:
            added.update(new)
            async_add_entities([EversoloBrightness(coordinator, entry, kind) for kind in new])

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


class EversoloBrightness(EversoloEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, kind: str) -> None:
        super().__init__(coordinator, entry, BRIGHTNESS_KINDS[kind])
        self._attr_translation_key = BRIGHTNESS_KINDS[kind]
        self._kind = kind

    @property
    def _data(self) -> dict:
        return self.coordinator.brightness.get(self._kind) or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self._data)

    @property
    def native_min_value(self) -> float:
        return self._data.get("min", 0)

    @property
    def native_max_value(self) -> float:
        return self._data.get("max", 100)

    @property
    def native_value(self) -> float | None:
        return self._data.get("value")

    async def async_set_native_value(self, value: float) -> None:
        value = int(max(self.native_min_value, min(self.native_max_value, round(value))))
        await self.coordinator.api.set_brightness(self._kind, value)
        # Show what the player really took: it may ignore the value (e.g. display brightness
        # while its screen is switched off).
        await asyncio.sleep(0.3)
        actual = await self.coordinator.api.get_brightness(self._kind)
        self.coordinator.brightness[self._kind] = actual or {**self._data, "value": value}
        self.coordinator.async_update_listeners()
