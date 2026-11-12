"""Select entities: input and output on the device."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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

    added: set[str] = set()

    @callback
    def _add() -> None:
        new = [key for key in coordinator.dsp if key not in added]
        if new:
            added.update(new)
            async_add_entities([EversoloDspConfigSelect(coordinator, entry, key) for key in new])

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


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



class EversoloDspConfigSelect(EversoloEntity, SelectEntity):
    """Which DSP / EQ config the current source uses (configs are made in the app)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator, entry, f"{key}_config")
        self._attr_translation_key = f"{key}_config"
        self._key = key

    @property
    def _entry_data(self) -> dict:
        return self.coordinator.dsp.get(self._key) or {}

    @property
    def available(self) -> bool:
        return super().available and bool(self._entry_data.get("configs"))

    @property
    def options(self) -> list[str]:
        return [c["name"] for c in self._entry_data.get("configs", [])]

    @property
    def current_option(self) -> str | None:
        source = self._entry_data.get("source") or {}
        for config in self._entry_data.get("configs", []):
            if config["id"] == source.get("eqId"):
                return config["name"]
        return None

    async def async_select_option(self, option: str) -> None:
        for config in self._entry_data.get("configs", []):
            if config["name"] == option:
                await self.coordinator.async_set_dsp(self._key, config_id=config["id"])
                return
