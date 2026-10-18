"""Media player entity for Eversolo."""
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EversoloCoordinator


def _nested_dict(data: Any, *path: str) -> dict[str, Any]:
    value = data
    for key in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(key)
    return value if isinstance(value, dict) else {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([EversoloMediaPlayer(hass.data[DOMAIN][entry.entry_id], entry)])


class EversoloMediaPlayer(CoordinatorEntity[EversoloCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = "Player"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.SEEK
    )

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_{coordinator.port}".replace(".", "_")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.host}:{coordinator.port}")},
            name=entry.data.get("name", f"Eversolo ({coordinator.host})"),
            manufacturer=MANUFACTURER,
            model=entry.data.get("name"),
            configuration_url=f"http://{coordinator.host}:{coordinator.port}",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def state(self):
        raw = (self.coordinator.data or {}).get("state")
        info = _nested_dict(raw, "everSoloPlayInfo")
        value = info.get("playStatus")
        if value is None:
            value = raw.get("state") if isinstance(raw, dict) else raw
        if isinstance(value, (int, float)):
            # DMP-A6 response: everSoloPlayInfo.playStatus == 2 while playing.
            if value == 2:
                return MediaPlayerState.PLAYING
            if value == 1:
                return MediaPlayerState.PAUSED
            if value == 0:
                return MediaPlayerState.IDLE
        text = str(value).lower() if value is not None else ""
        if "pause" in text:
            return MediaPlayerState.PAUSED
        if "play" in text:
            return MediaPlayerState.PLAYING
        if "stop" in text or "idle" in text:
            return MediaPlayerState.IDLE
        return None

    @property
    def volume_level(self):
        data = self.coordinator.data or {}
        state_data = data.get("state")
        volume_data = _nested_dict(state_data, "volumeData")
        if not volume_data:
            volume_data = _nested_dict(data.get("volume"), "volumeData")
        value = volume_data.get("currenttVolume")
        maximum = volume_data.get("maxVolume", 200)
        try:
            maximum = float(maximum)
            return max(0.0, min(1.0, float(value) / maximum)) if maximum > 0 else None
        except (TypeError, ValueError):
            return None

    @property
    def media_title(self):
        music = _nested_dict((self.coordinator.data or {}).get("state"), "playingMusic")
        value = music.get("title")
        return str(value) if value is not None else None

    @property
    def media_artist(self):
        music = _nested_dict((self.coordinator.data or {}).get("state"), "playingMusic")
        value = music.get("artist")
        return str(value) if value is not None else None

    @property
    def media_album_name(self):
        music = _nested_dict((self.coordinator.data or {}).get("state"), "playingMusic")
        value = music.get("album")
        return str(value) if value is not None else None

    @property
    def media_image_url(self):
        music = _nested_dict((self.coordinator.data or {}).get("state"), "playingMusic")
        value = music.get("albumArt")
        return str(value) if value else None

    @property
    def media_duration(self):
        raw = (self.coordinator.data or {}).get("state")
        try:
            # The API reports position and duration in milliseconds.
            return float(raw["duration"]) / 1000 if isinstance(raw, dict) and raw.get("duration") is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def media_position(self):
        raw = (self.coordinator.data or {}).get("state")
        try:
            return float(raw["position"]) / 1000 if isinstance(raw, dict) and raw.get("position") is not None else None
        except (TypeError, ValueError):
            return None

    async def async_media_play(self):
        if self.state != MediaPlayerState.PLAYING:
            await self.coordinator.client.async_play_pause()
            await self.coordinator.async_request_refresh()

    async def async_media_pause(self):
        if self.state == MediaPlayerState.PLAYING:
            await self.coordinator.client.async_play_pause()
            await self.coordinator.async_request_refresh()

    async def async_media_play_pause(self):
        await self.coordinator.client.async_play_pause()
        await self.coordinator.async_request_refresh()

    async def async_media_next_track(self):
        await self.coordinator.client.async_next()
        await self.coordinator.async_request_refresh()

    async def async_media_previous_track(self):
        await self.coordinator.client.async_previous()
        await self.coordinator.async_request_refresh()

    async def async_media_seek(self, position: float):
        await self.coordinator.client.async_seek(position)
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float):
        await self.coordinator.client.async_set_volume(volume)
        await self.coordinator.async_request_refresh()
