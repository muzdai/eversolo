"""Polling coordinator: getState and the input/output list every 2 s, like the app does."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EversoloApi, EversoloError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS, SLOW_REFRESH_SECONDS

_LOGGER = logging.getLogger(__name__)


class EversoloCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest getState payload plus inputs/outputs, power menu and apps."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi, name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.io: dict[str, list[dict]] = {"inputs": [], "outputs": []}
        self.power_options: list[dict] = []
        self.apps: list[dict] = []
        self.last_app: str | None = None
        self.last_update_success_time: datetime | None = None
        self._slow_at: float | None = None

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
