"""Polling coordinator: getState and the input/output list every 2 s, like the app does."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EversoloApi, EversoloError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class EversoloCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest getState payload and the input/output lists."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi, name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.io: dict[str, list[dict]] = {"inputs": [], "outputs": []}
        self.last_update_success_time = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.get_state()
        except EversoloError as err:
            raise UpdateFailed(str(err)) from err
        try:
            self.io = await self.api.get_io()
        except EversoloError as err:
            _LOGGER.debug("Input/output list unavailable: %s", err)
        self.last_update_success_time = dt_util.utcnow()
        return state
