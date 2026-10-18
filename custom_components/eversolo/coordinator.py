"""Local HTTP client and polling coordinator for Eversolo."""
import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class EversoloApiError(Exception):
    """Local API request failed."""


class EversoloClient:
    """Client for Eversolo's local HTTP API."""

    def __init__(self, hass: HomeAssistant, host: str, port: int = 9529):
        self._session = async_get_clientsession(hass)
        self.host, self.port = host, int(port)
        self.base_url = f"http://{host}:{self.port}"

    async def async_request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                response.raise_for_status()
                body = await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EversoloApiError(f"{path}: {err}") from err
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return body.strip()

    async def async_get_model(self) -> str | None:
        try:
            data = await self.async_request("/ZidooControlCenter/getModel")
        except EversoloApiError:
            data = await self.async_request("/ZidooMusicControl/v2/getState")
        if isinstance(data, dict):
            device = data.get("deviceInfo", {})
            if isinstance(device, dict):
                for key in ("model", "deviceName", "name"):
                    if isinstance(device.get(key), str):
                        return device[key]
            for key in ("model", "modelName", "deviceName", "name"):
                if isinstance(data.get(key), str):
                    return data[key]
        return None

    async def async_get_state(self):
        return await self.async_request("/ZidooMusicControl/v2/getState")

    async def async_get_volume(self):
        return await self.async_request("/ZidooMusicControl/v2/getVolume")

    async def async_play_pause(self):
        await self.async_request("/ZidooControlCenter/RemoteControl/sendkey", {"key": "Key.MediaPlay.Pause"})

    async def async_next(self):
        await self.async_request("/ZidooControlCenter/RemoteControl/sendkey", {"key": "Key.MediaNext"})

    async def async_previous(self):
        await self.async_request("/ZidooControlCenter/RemoteControl/sendkey", {"key": "Key.MediaPrev"})

    async def async_seek(self, position: float):
        await self.async_request("/ZidooMusicControl/v2/seekTo", {"time": str(int(position * 1000))})

    async def async_set_volume(self, volume: float):
        # getVolume reports maxVolume=200 on the user's DMP-A6 firmware.
        value = round(max(0.0, min(1.0, volume)) * 200)
        await self.async_request("/ZidooMusicControl/v2/setDevicesVolume", {"volume": str(value)})

class EversoloCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, host: str, port: int):
        self.client = EversoloClient(hass, host, port)
        self.host, self.port = host, port
        super().__init__(
            hass,
            _LOGGER,
            name=f"Eversolo {host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self):
        state_result, volume_result = await asyncio.gather(
            self.client.async_get_state(),
            self.client.async_get_volume(),
            return_exceptions=True,
        )
        if isinstance(state_result, Exception):
            raise UpdateFailed(str(state_result)) from state_result
        volume = None if isinstance(volume_result, Exception) else volume_result
        if isinstance(volume_result, Exception):
            _LOGGER.debug("Eversolo volume poll failed: %s", volume_result)
        return {"state": state_result, "volume": volume}
