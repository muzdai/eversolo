"""Select entities: inputs, outputs, VU/spectrum view."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VU_OPEN_TYPE
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity

VU_OPTIONS = {"vu": "VU meter", "spectrum": "Spectrum"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            EversoloListSelect(coordinator, entry, "input", "Input", "inputs"),
            EversoloListSelect(coordinator, entry, "output", "Output", "outputs"),
            EversoloVuSelect(coordinator, entry),
        ]
    )


class EversoloListSelect(EversoloEntity, SelectEntity):
    def __init__(self, coordinator, entry, key, label, bucket) -> None:
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key
        self._attr_name = label
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
                await self.coordinator.async_request_refresh()
                return


class EversoloVuSelect(EversoloEntity, SelectEntity):
    _attr_name = "Meter display"
    _attr_options = list(VU_OPTIONS.values())

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "vu")
        self._attr_translation_key = "vu"

    @property
    def current_option(self) -> str | None:
        mode = {0: "vu", 1: "spectrum"}.get(self.coordinator.data.get("vuDisplayMode"))
        return VU_OPTIONS.get(mode)

    async def async_select_option(self, option: str) -> None:
        mode = next(k for k, v in VU_OPTIONS.items() if v == option)
        await self.coordinator.api.set_vu(VU_OPEN_TYPE[mode])
        await self.coordinator.async_request_refresh()
