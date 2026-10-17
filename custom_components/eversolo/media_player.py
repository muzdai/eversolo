"""Media player entity for Eversolo."""
from typing import Any
from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, MANUFACTURER
from .coordinator import EversoloCoordinator

def _dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, dict):
                yield from _dicts(child)
            elif isinstance(child, list):
                for item in child:
                    yield from _dicts(item)

def _find(data: Any, keys: tuple[str, ...]):
    for item in _dicts(data):
        for key in keys:
            if item.get(key) is not None:
                return item[key]
    return None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([EversoloMediaPlayer(hass.data[DOMAIN][entry.entry_id], entry)])

class EversoloMediaPlayer(CoordinatorEntity[EversoloCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = "Player"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE |
        MediaPlayerEntityFeature.PLAY_PAUSE | MediaPlayerEntityFeature.NEXT_TRACK |
        MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.VOLUME_SET |
        MediaPlayerEntityFeature.SEEK
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
        raw = self.coordinator.data.get("state") if self.coordinator.data else None
        value = _find(raw, ("playState", "playStatus", "status", "state", "playerState"))
        if value is None and isinstance(raw, str):
            value = raw
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
        raw = self.coordinator.data.get("volume") if self.coordinator.data else None
        value = _find(raw, ("volume", "currentVolume", "soundVolume", "value", "level"))
        if value is None and isinstance(raw, (int, float)):
            value = raw
        try:
            return max(0.0, min(1.0, float(value) / 100))
        except (TypeError, ValueError):
            return None

    @property
    def media_title(self):
        raw = self.coordinator.data.get("state") if self.coordinator.data else None
        value = _find(raw, ("title", "musicName", "songName", "trackName"))
        return str(value) if value is not None else None

    @property
    def media_artist(self):
        raw = self.coordinator.data.get("state") if self.coordinator.data else None
        value = _find(raw, ("artist", "artistName", "singer", "author"))
        return str(value) if value is not None else None

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