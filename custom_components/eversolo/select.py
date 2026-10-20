"""Select entities: input, output and streaming app on the device."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            EversoloListSelect(coordinator, entry, "input", "inputs"),
            EversoloListSelect(coordinator, entry, "output", "outputs"),
            EversoloAppSelect(coordinator, entry),
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
                await self.coordinator.async_request_refresh()
                return


class EversoloAppSelect(EversoloEntity, SelectEntity):
    """Open a streaming app installed on the device (Tidal, Qobuz, ...).

    The device does not report which app is in front, so the state is the
    last app opened from Home Assistant in this session.
    """

    _attr_translation_key = "app"

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "app")

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.apps)

    @property
    def options(self) -> list[str]:
        return [a["name"] for a in self.coordinator.apps]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.last_app if self.coordinator.last_app in self.options else None

    async def async_select_option(self, option: str) -> None:
        for app in self.coordinator.apps:
            if app["name"] == option:
                await self.coordinator.api.open_app(app["package"])
                self.coordinator.last_app = option
                self.coordinator.async_update_listeners()
                return
