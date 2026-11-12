"""Power switch: on = Wake on LAN, off = the device's own power-off command (see power.py)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity

# key -> (getState flag "the function exists for the current source/output", "it is switched on")
DSP_FLAGS = {"dsp": "hasDspSetting", "eq": "hasEQSetting"}
DSP_ACTIVE = {"dsp": "dspActive", "eq": "eqActive"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPowerSwitch(coordinator, entry)])

    # DSP (analog outputs) and EQ (digital outputs): added when the player reports the function.
    added: set[str] = set()

    @callback
    def _add() -> None:
        data = coordinator.data or {}
        new = [key for key, flag in DSP_FLAGS.items() if data.get(flag) and key not in added]
        if new:
            added.update(new)
            async_add_entities([EversoloDspSwitch(coordinator, entry, key) for key in new])

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


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


class EversoloDspSwitch(EversoloEntity, SwitchEntity):
    """DSP or EQ for the current source, as on the app's DSP page (per input, with its config)."""

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key
        self._key = key

    @property
    def available(self) -> bool:
        # The player offers DSP on analog outputs and EQ on digital ones, per source.
        return super().available and bool((self.coordinator.data or {}).get(DSP_FLAGS[self._key]))

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get(DSP_ACTIVE[self._key]))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source = (self.coordinator.dsp.get(self._key) or {}).get("source") or {}
        return {"source": source.get("name"), "config": source.get("configName")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_dsp(self._key, enable=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_dsp(self._key, enable=False)
