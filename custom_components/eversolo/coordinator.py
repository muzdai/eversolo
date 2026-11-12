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
from .power import PowerControl
from .const import (
    CONFIRM_DELAY_SECONDS,
    DOMAIN,
    OFFLINE_AFTER_FAILURES,
    OFFLINE_SCAN_INTERVAL_SECONDS,
    SCAN_INTERVAL_SECONDS,
    SLOW_REFRESH_SECONDS,
)

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
        # "Screen" / "Knob" -> {value, min, max}; only what this model has.
        self.brightness: dict[str, dict] = {}
        # "dsp" / "eq" -> {"source": {...}, "configs": [{id, name}]}; only what applies to the current source.
        self.dsp: dict[str, dict] = {}
        self._dsp_key: tuple | None = None
        self.last_update_success_time: datetime | None = None
        self._slow_at: float | None = None
        self._confirm_unsub: CALLBACK_TYPE | None = None
        self._failures = 0
        self._fast_until = 0.0
        self.power: PowerControl | None = None  # set in async_setup_entry

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.get_state()
        except EversoloError as err:
            self._failures += 1
            if self.data is not None and self.last_update_success and self._failures < OFFLINE_AFTER_FAILURES:
                # A single lost answer: keep showing the last state instead of flapping to unavailable.
                _LOGGER.debug("No answer (%s of %s): %s", self._failures, OFFLINE_AFTER_FAILURES, err)
                return self.data
            if time.monotonic() >= self._fast_until:
                self.update_interval = timedelta(seconds=OFFLINE_SCAN_INTERVAL_SECONDS)
            raise UpdateFailed(str(err)) from err
        self._failures = 0
        self.update_interval = timedelta(seconds=SCAN_INTERVAL_SECONDS)
        try:
            self.io = await self.api.get_io()
        except EversoloError as err:
            _LOGGER.debug("Input/output list unavailable: %s", err)

        now = time.monotonic()
        if self._slow_at is None or now - self._slow_at > SLOW_REFRESH_SECONDS:
            self._slow_at = now
            await self._async_refresh_slow()

        # DSP / EQ assignment belongs to the current input and output: read it again when they change.
        dsp_key = (
            tuple(i["tag"] for b in ("inputs", "outputs") for i in self.io[b] if i["selected"]),
            state.get("hasDspSetting"), state.get("hasEQSetting"), state.get("dspActive"), state.get("eqActive"),
        )
        if dsp_key != self._dsp_key:
            self._dsp_key = dsp_key
            await self.async_refresh_dsp(state)

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
        for kind in ("Screen", "Knob"):
            try:
                value = await self.api.get_brightness(kind)
            except EversoloError as err:
                _LOGGER.debug("%s brightness unavailable: %s", kind, err)
                continue
            if value:
                self.brightness[kind] = value
            else:
                self.brightness.pop(kind, None)

    async def async_refresh_dsp(self, state: dict[str, Any] | None = None) -> None:
        state = state if state is not None else (self.data or {})
        for key, is_dsp, flag in (("dsp", True, "hasDspSetting"), ("eq", False, "hasEQSetting")):
            if not state.get(flag):
                self.dsp.pop(key, None)
                continue
            try:
                source = await self.api.get_dsp_source(is_dsp)
                configs = await self.api.get_dsp_configs(is_dsp) if source else []
            except EversoloError as err:
                _LOGGER.debug("%s settings unavailable: %s", key, err)
                continue
            if source:
                self.dsp[key] = {"source": source, "configs": configs}
            else:
                self.dsp.pop(key, None)

    async def async_set_dsp(self, key: str, enable: bool | None = None, config_id: int | None = None) -> None:
        """Switch DSP / EQ for the current source, or give it another config."""
        await self.async_refresh_dsp()  # the source may have changed since the last read
        entry = self.dsp.get(key)
        if not entry:
            raise EversoloError("DSP / EQ is not available for the current source and output")
        source = entry["source"]
        enable = bool(source.get("enable")) if enable is None else enable
        config_id = source.get("eqId") if config_id is None else config_id
        await self.api.set_dsp_source(source, enable, config_id)
        name = next((c["name"] for c in entry["configs"] if c["id"] == config_id), source.get("configName"))
        entry["source"] = {**source, "enable": enable, "eqId": config_id, "configName": name}
        self.apply(state={"dspActive" if key == "dsp" else "eqActive": enable})

    @callback
    def poll_fast(self, seconds: float) -> None:
        """Keep the normal 2 s polling for a while although the player is offline (it was just woken)."""
        self._fast_until = time.monotonic() + seconds
        self.update_interval = timedelta(seconds=SCAN_INTERVAL_SECONDS)

    @property
    def command_pending(self) -> bool:
        """A command was just sent and the device has not been read back yet."""
        return self._confirm_unsub is not None

    @callback
    def async_shutdown_timers(self) -> None:
        if self._confirm_unsub:
            self._confirm_unsub()
            self._confirm_unsub = None
        if self.power:
            self.power.async_cancel()

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
