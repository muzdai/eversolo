"""Power on / off for one player: Wake on LAN to switch on, the player's own power menu to switch off.

Shared by the power switch and the media player (turn_on / turn_off), so both show the same state.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_BROADCAST,
    CONF_HOST,
    CONF_MAC,
    POWER_OFF_TAGS,
    SWITCH_OFF_GRACE_SECONDS,
    SWITCH_ON_GRACE_SECONDS,
)
from . import wol

if TYPE_CHECKING:
    from .coordinator import EversoloCoordinator


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


class PowerControl:
    """On while the player answers.

    The player needs a while to boot or shut down, so the requested state is shown until the
    device catches up or a grace period runs out.
    """

    def __init__(self, hass: HomeAssistant, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._pending: bool | None = None
        self._pending_until = 0.0
        self._pending_unsub: CALLBACK_TYPE | None = None

    @property
    def mac(self) -> str | None:
        return self.entry.data.get(CONF_MAC)

    @property
    def can_wake(self) -> bool:
        return bool(self.mac)

    @property
    def is_on(self) -> bool:
        online = self.coordinator.last_update_success
        if self._pending is not None:
            if time.monotonic() < self._pending_until and online != self._pending:
                return self._pending
            self._pending = None
        return online

    @callback
    def _expect(self, state: bool, seconds: float) -> None:
        self._pending = state
        self._pending_until = time.monotonic() + seconds
        self.coordinator.async_update_listeners()
        # The coordinator does not notify entities about repeated failed polls, so a player
        # that never woke up would stay "on" forever: re-evaluate when the grace period ends.
        self.async_cancel()
        self._pending_unsub = async_call_later(self.hass, seconds + 0.5, self._async_grace_over)

    @callback
    def _async_grace_over(self, _now: Any) -> None:
        self._pending_unsub = None
        self.coordinator.async_update_listeners()

    @callback
    def async_cancel(self) -> None:
        if self._pending_unsub:
            self._pending_unsub()
            self._pending_unsub = None

    async def async_turn_on(self) -> None:
        if not self.mac:
            raise HomeAssistantError(
                "The player's MAC address is not known yet: switch it on once by hand, "
                "or enter it in the integration settings"
            )
        await wol.async_wake(self.hass, self.mac, self.entry.data[CONF_HOST], self.entry.data.get(CONF_BROADCAST))
        self._expect(True, SWITCH_ON_GRACE_SECONDS)
        self.coordinator.poll_fast(SWITCH_ON_GRACE_SECONDS)
        # Polling again reschedules the next poll with the fast interval.
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        coordinator = self.coordinator
        tag = power_off_tag(coordinator.power_options)
        if tag is None:
            if not coordinator.last_update_success:
                return  # already off
            # Power menu not read yet (the player was just woken): ask for it now.
            coordinator.power_options = await coordinator.api.get_power_options()
            tag = power_off_tag(coordinator.power_options)
        if tag is None:
            raise HomeAssistantError("This player has no power-off entry in its power menu")
        await coordinator.api.power(tag)
        self._expect(False, SWITCH_OFF_GRACE_SECONDS)
