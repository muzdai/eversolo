"""Polling coordinator: getState every few seconds, slow data once a minute."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EversoloApi, EversoloError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS, SLOW_REFRESH_SECONDS

_LOGGER = logging.getLogger(__name__)


class EversoloCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest getState payload plus input/output/service lists."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi, name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.io: dict[str, list[dict]] = {"inputs": [], "outputs": []}
        self.services: list[dict] = []
        self.display_on: bool | None = None  # optimistic, device does not report it (see README)
        self._slow_at: float | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.get_state()
        except EversoloError as err:
            raise UpdateFailed(str(err)) from err

        now = time.monotonic()
        if self._slow_at is None or now - self._slow_at > SLOW_REFRESH_SECONDS:
            self._slow_at = now
            try:
                self.io = await self.api.get_io()
            except EversoloError as err:
                _LOGGER.debug("Input/output list unavailable: %s", err)
            try:
                self.services = await self.api.get_services()
            except EversoloError as err:
                _LOGGER.debug("Service list unavailable: %s", err)
        return state
