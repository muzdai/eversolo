"""Power switch: on = Wake on LAN, off = the device's own power-off command."""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_BROADCAST,
    CONF_HOST,
    CONF_MAC,
    DOMAIN,
    POWER_OFF_TAGS,
    SWITCH_OFF_GRACE_SECONDS,
    SWITCH_ON_GRACE_SECONDS,
)
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity
from .wol import async_wake


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPowerSwitch(coordinator, entry)])


def power_off_tag(options: list[dict]) -> str | None:
    """The power-menu entry that switches the player off (poweroff on DMP-A6 / A8)."""
    tags = [o["tag"] for o in options]
    for wanted in POWER_OFF_TAGS:
        if wanted in tags:
            return wanted
    for tag in tags:
        if "off" in tag.lower() and "screen" not in tag.lower():
            return tag
    return None


class EversoloPowerSwitch(EversoloEntity, SwitchEntity):
    """On while the player answers. Turning on sends a magic packet, turning off sends power-off.

    The player needs a while to boot or shut down, so the requested state is shown until the
    device catches up (or a grace period runs out).
    """

    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "power")
        self._pending: bool | None = None
        self._pending_until = 0.0
        self._pending_unsub: CALLBACK_TYPE | None = None

    @property
    def _mac(self) -> str | None:
        return self._entry.data.get(CONF_MAC)

    @property
    def available(self) -> bool:
        # Must stay usable while the player is off, as long as we know where to send the packet.
        return self.coordinator.last_update_success or bool(self._mac)

    @property
    def is_on(self) -> bool:
        online = self.coordinator.last_update_success
        if self._pending is not None:
            if time.monotonic() < self._pending_until and online != self._pending:
                return self._pending
            self._pending = None
        return online

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mac": self._mac}

    @callback
    def _expect(self, state: bool, seconds: float) -> None:
        self._pending = state
        self._pending_until = time.monotonic() + seconds
        self.async_write_ha_state()
        # The coordinator does not notify entities about repeated failed polls, so a player
        # that never woke up would stay "on" forever: re-evaluate when the grace period ends.
        self._cancel_pending_timer()
        self._pending_unsub = async_call_later(self.hass, seconds + 0.5, self._async_grace_over)

    @callback
    def _async_grace_over(self, _now: Any) -> None:
        self._pending_unsub = None
        self.async_write_ha_state()

    @callback
    def _cancel_pending_timer(self) -> None:
        if self._pending_unsub:
            self._pending_unsub()
            self._pending_unsub = None

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_pending_timer()

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._mac:
            raise HomeAssistantError(
                "The player's MAC address is not known yet: switch it on once by hand, "
                "or enter it in the integration settings"
            )
        await async_wake(self.hass, self._mac, self._entry.data[CONF_HOST], self._entry.data.get(CONF_BROADCAST))
        self._expect(True, SWITCH_ON_GRACE_SECONDS)

    async def async_turn_off(self, **kwargs: Any) -> None:
        tag = power_off_tag(self.coordinator.power_options)
        if tag is None:
            if not self.coordinator.last_update_success:
                return  # already off
            # Power menu not read yet (the player was just woken): ask for it now.
            self.coordinator.power_options = await self.coordinator.api.get_power_options()
            tag = power_off_tag(self.coordinator.power_options)
        if tag is None:
            raise HomeAssistantError("This player has no power-off entry in its power menu")
        await self.coordinator.api.power(tag)
        self._expect(False, SWITCH_OFF_GRACE_SECONDS)
