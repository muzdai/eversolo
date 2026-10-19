"""Media player entity: transport, volume, seek, cover art and card attributes."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    LOOP_LIST,
    LOOP_SHUFFLE,
    LOOP_SINGLE,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_PREPARED,
    STATE_PREPARING,
)
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity

# getState reports durations in one unit (ms on current firmware, verify); we detect it.
MS_THRESHOLD = 20000

FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SHUFFLE_SET
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPlayer(coordinator, entry)])


class EversoloPlayer(EversoloEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_supported_features = FEATURES
    _attr_media_image_remotely_accessible = False

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "player")
        self._last_art: str | None = None

    # ---- helpers -------------------------------------------------------
    @property
    def _state(self) -> dict:
        return self.coordinator.data or {}

    @property
    def _music(self) -> dict:
        return self._state.get("playingMusic") or {}

    @property
    def _volume(self) -> dict:
        return self._state.get("volumeData") or {}

    def _to_seconds(self, value: int | float) -> float:
        return value / 1000 if self._is_ms() else float(value)

    def _is_ms(self) -> bool:
        return (self._state.get("duration") or 0) > MS_THRESHOLD

    def _selected(self, items: list[dict]) -> str | None:
        for item in items:
            if item["selected"]:
                return item["name"]
        return None

    # ---- state ---------------------------------------------------------
    @property
    def state(self) -> MediaPlayerState:
        if not self.available:
            return MediaPlayerState.UNAVAILABLE
        st = self._state.get("state")
        if st == STATE_PLAYING:
            return MediaPlayerState.PLAYING
        if st == STATE_PAUSED:
            return MediaPlayerState.PAUSED
        if st in (STATE_PREPARING, STATE_PREPARED):
            return MediaPlayerState.BUFFERING
        return MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        return self._music.get("name") or self._music.get("title") or None

    @property
    def media_artist(self) -> str | None:
        return self._music.get("artist") or None

    @property
    def media_album_name(self) -> str | None:
        return self._music.get("album") or None

    @property
    def media_duration(self) -> float | None:
        dur = self._state.get("duration")
        return self._to_seconds(dur) if dur else None

    @property
    def media_position(self) -> float | None:
        pos = self._state.get("position")
        return self._to_seconds(pos) if pos is not None else None

    @property
    def media_position_updated_at(self) -> datetime | None:
        return self.coordinator.last_update_success_time

    @property
    def volume_level(self) -> float | None:
        cur, mx = self._volume.get("currenttVolume"), self._volume.get("maxVolume")
        if cur is None or not mx:
            return None
        return max(0.0, min(1.0, cur / mx))

    @property
    def is_volume_muted(self) -> bool | None:
        return self._volume.get("isMute")

    @property
    def repeat(self) -> RepeatMode:
        return {LOOP_LIST: RepeatMode.OFF, LOOP_SINGLE: RepeatMode.ONE, LOOP_SHUFFLE: RepeatMode.ALL}.get(
            self._state.get("loopModel"), RepeatMode.OFF
        )

    @property
    def shuffle(self) -> bool:
        return self._state.get("loopModel") == LOOP_SHUFFLE

    @property
    def source_list(self) -> list[str]:
        return [i["name"] for i in self.coordinator.io["inputs"]]

    @property
    def source(self) -> str | None:
        return self._selected(self.coordinator.io["inputs"])

    @property
    def media_image_hash(self) -> str | None:
        art = self._music.get("albumArtBig") or self._music.get("albumArt")
        if not art:
            return None
        return hashlib.md5(art.encode()).hexdigest()

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        result = await self.coordinator.api.get_cover(self._music)
        return result if result else (None, None)

    @property
    def extra_state_attributes(self) -> dict:
        io = self.coordinator.io
        vu_mode = self._state.get("vuDisplayMode")
        vol = self._volume
        return {
            "input": self._selected(io["inputs"]),
            "input_list": [i["name"] for i in io["inputs"]],
            "output": self._selected(io["outputs"]),
            "output_list": [i["name"] for i in io["outputs"]],
            "service": self._selected(self.coordinator.services),
            "service_list": [i["name"] for i in self.coordinator.services],
            "vu_mode": {0: "vu", 1: "spectrum"}.get(vu_mode),
            "display_on": self.coordinator.display_on,
            "loop_mode": {LOOP_LIST: "list", LOOP_SINGLE: "single", LOOP_SHUFFLE: "shuffle"}.get(
                self._state.get("loopModel"), "list"
            ),
            "album_artist": self._music.get("albumArtist"),
            "codec": self._music.get("codec") or (self._state.get("everSoloPlayInfo") or {}).get("audioDecodec"),
            "sample_rate": self._music.get("sampleRate"),
            "bits": self._music.get("bits"),
            "volume_tag": vol.get("volumeTag"),
            "host": self.coordinator.api.host,
        }

    # ---- actions -------------------------------------------------------
    async def async_media_play(self) -> None:
        if self.state != MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            await self.coordinator.async_request_refresh()

    async def async_media_next_track(self) -> None:
        await self.coordinator.api.next_track()
        await self.coordinator.async_request_refresh()

    async def async_media_previous_track(self) -> None:
        await self.coordinator.api.previous_track()
        await self.coordinator.async_request_refresh()

    async def async_media_seek(self, position: float) -> None:
        value = position * 1000 if self._is_ms() else position
        await self.coordinator.api.seek(int(value))
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        mx = self._volume.get("maxVolume") or 100
        await self.coordinator.api.set_volume(round(volume * mx))
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        if bool(self.is_volume_muted) != mute:
            await self.coordinator.api.key("Mute")
            await self.coordinator.async_request_refresh()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        mode = {RepeatMode.OFF: LOOP_LIST, RepeatMode.ONE: LOOP_SINGLE, RepeatMode.ALL: LOOP_SHUFFLE}[repeat]
        await self.coordinator.api.set_loop(mode)
        await self.coordinator.async_request_refresh()

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self.coordinator.api.set_loop(LOOP_SHUFFLE if shuffle else LOOP_LIST)
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        for item in self.coordinator.io["inputs"]:
            if item["name"] == source:
                await self.coordinator.api.set_input(item["tag"])
                await self.coordinator.async_request_refresh()
                return
