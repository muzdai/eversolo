"""Select entities: input and output on the device."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    # The "Streaming app" select was removed in 2.5.1; drop its registry entry.
    registry = er.async_get(hass)
    if old := registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_app"):
        registry.async_remove(old)
    async_add_entities(
        [
            EversoloListSelect(coordinator, entry, "input", "inputs"),
            EversoloListSelect(coordinator, entry, "output", "outputs"),
        ]
    )


class EversoloListSelect(EversoloEntity, SelectEntity):
    """Input or output, read from getInputAndOutputList and set like the app does."""

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, key: str, bucket: str) -> None:
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key
        self._bucket = bucket

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.io[self._bucket])

    @property
    def options(self) -> list[str]:
        return [i["name"] for i in self.coordinator.io[self._bucket]]

    @property
    def current_option(self) -> str | None:
        for item in self.coordinator.io[self._bucket]:
            if item["selected"]:
                return item["name"]
        return None

    async def async_select_option(self, option: str) -> None:
        for item in self.coordinator.io[self._bucket]:
            if item["name"] == option:
                if self._bucket == "inputs":
                    await self.coordinator.api.set_input(item["tag"], item["index"])
                else:
                    await self.coordinator.api.set_output(item["tag"], item["index"])
                self.coordinator.select_io(self._bucket, item["index"])
                return

