"""Polling coordinator: getState and the input/output list every 2 s, like the app does."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EversoloApi, EversoloError
from .const import CONFIRM_DELAY_SECONDS, DOMAIN, SCAN_INTERVAL_SECONDS, SLOW_REFRESH_SECONDS

_LOGGER = logging.getLogger(__name__)


class EversoloCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest getState payload plus inputs/outputs, power menu and apps."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi, name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            # The default 10 s cooldown delayed every second action in a row.
            request_refresh_debouncer=Debouncer(hass, _LOGGER, cooldown=0.3, immediate=True),
        )
        self.api = api
        self.io: dict[str, list[dict]] = {"inputs": [], "outputs": []}
        self.power_options: list[dict] = []
        self.apps: list[dict] = []
        self.last_app: str | None = None
        self.last_update_success_time: datetime | None = None
        self._slow_at: float | None = None
        self._confirm_unsub: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.get_state()
        except EversoloError as err:
            raise UpdateFailed(str(err)) from err
        try:
            self.io = await self.api.get_io()
        except EversoloError as err:
            _LOGGER.debug("Input/output list unavailable: %s", err)

        now = time.monotonic()
        if self._slow_at is None or now - self._slow_at > SLOW_REFRESH_SECONDS:
            self._slow_at = now
            await self._async_refresh_slow()

        self.last_update_success_time = dt_util.utcnow()
        return state

    async def _async_refresh_slow(self) -> None:
        try:
            self.power_options = await self.api.get_power_options()
        except EversoloError as err:
            _LOGGER.debug("Power options unavailable: %s", err)
        try:
            self.apps = await self.api.get_apps()
        except EversoloError as err:
            _LOGGER.debug("App list unavailable: %s", err)

    # ---- instant feedback ------------------------------------------------
    @callback
    def apply(
        self,
        state: dict[str, Any] | None = None,
        volume: dict[str, Any] | None = None,
        info: dict[str, Any] | None = None,
    ) -> None:
        """Show the expected result of a command right away, then confirm with the device.

        The device needs a moment to act on a command, so reading it back at once
        would show the old state and make the UI jump back and forth.
        """
        data = dict(self.data or {})
        if state:
            data.update(state)
        if volume:
            data["volumeData"] = {**(data.get("volumeData") or {}), **volume}
        if info:
            data["everSoloPlayInfo"] = {**(data.get("everSoloPlayInfo") or {}), **info}
        self.last_update_success_time = dt_util.utcnow()
        self.async_set_updated_data(data)
        self.confirm_later()

    @callback
    def confirm_later(self, delay: float = CONFIRM_DELAY_SECONDS) -> None:
        """Read the device again shortly after a command (one pending check at a time)."""
        if self._confirm_unsub:
            self._confirm_unsub()
        self._confirm_unsub = async_call_later(self.hass, delay, self._async_confirm)

    async def _async_confirm(self, _now: Any) -> None:
        self._confirm_unsub = None
        await self.async_refresh()

    @callback
    def select_io(self, bucket: str, index: int) -> None:
        """Mark an input/output as current right away; the next read confirms it."""
        self.io[bucket] = [{**i, "selected": i["index"] == index} for i in self.io[bucket]]
        self.async_update_listeners()
        self.confirm_later()
