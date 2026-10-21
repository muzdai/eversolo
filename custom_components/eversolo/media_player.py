"""Media player entity: transport, volume, seek, cover art and card attributes."""
from __future__ import annotations

import hashlib
from datetime import datetime

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
    CONF_MODEL,
    DOMAIN,
    LOOP_NAMES,
    LOOP_PLAY_ONCE,
    LOOP_REPEAT_ALL,
    LOOP_REPEAT_ONE,
    LOOP_SHUFFLE,
    PLAY_STATUS_PLAYING,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_PREPARED,
    STATE_PREPARING,
)
from .coordinator import EversoloCoordinator
from .entity import EversoloEntity

TRANSPORT = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SEEK
)
VOLUME = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
)
OTHER = (
    MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

REPEAT_TO_LOOP = {RepeatMode.ALL: LOOP_REPEAT_ALL, RepeatMode.ONE: LOOP_REPEAT_ONE, RepeatMode.OFF: LOOP_PLAY_ONCE}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPlayer(coordinator, entry)])


class EversoloPlayer(EversoloEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_media_image_remotely_accessible = False

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "player")

    # ---- raw payload helpers ------------------------------------------
    @property
    def _state(self) -> dict:
        return self.coordinator.data or {}

    @property
    def _music(self) -> dict:
        """Library / internal player track (MusicState.playingMusic)."""
        return self._state.get("playingMusic") or {}

    @property
    def _info(self) -> dict:
        """Other sources (Bluetooth, streaming apps): MusicState.everSoloPlayInfo."""
        return self._state.get("everSoloPlayInfo") or {}

    @property
    def _audio(self) -> dict:
        return self._info.get("everSoloPlayAudioInfo") or {}

    @property
    def _output(self) -> dict:
        return self._info.get("everSoloPlayOutputInfo") or {}

    @property
    def _volume(self) -> dict:
        return self._state.get("volumeData") or {}

    @property
    def _external(self) -> bool:
        """True when nothing is loaded in the library player but another source reports playback."""
        return not self._music and bool(self._audio)

    @property
    def _use_audio(self) -> bool:
        """Same rule as PlaybackFragmentLand: playType 5 is the library, others use everSoloPlayAudioInfo."""
        if not self._audio.get("songName"):
            return False
        return not self._music or self._info.get("playType") not in (None, 5)

    @staticmethod
    def _selected(items: list[dict]) -> str | None:
        for item in items:
            if item["selected"]:
                return item["name"]
        return None

    # ---- state ---------------------------------------------------------
    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = OTHER
        vol = self._volume
        if vol.get("isVolumeEnable", True) and not vol.get("isLock"):
            features |= VOLUME
        if not self._external:
            return features | TRANSPORT
        # Mirror the app: it hides controls the current source cannot handle.
        info = self._info
        if info.get("isCanChangePlayStatus", True):
            features |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        if info.get("isCanNextPlay", True):
            features |= MediaPlayerEntityFeature.NEXT_TRACK
        if info.get("isCanLastPlay", True):
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        if info.get("isCanSeek", True):
            features |= MediaPlayerEntityFeature.SEEK
        return features

    @property
    def state(self) -> MediaPlayerState:
        st = self._state.get("state")
        if st == STATE_PLAYING:
            return MediaPlayerState.PLAYING
        if st == STATE_PAUSED:
            return MediaPlayerState.PAUSED
        if st in (STATE_PREPARING, STATE_PREPARED):
            return MediaPlayerState.BUFFERING
        if self._external:
            return (
                MediaPlayerState.PLAYING
                if self._info.get("playStatus") in PLAY_STATUS_PLAYING
                else MediaPlayerState.PAUSED
            )
        return MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        if self._use_audio:
            return self._audio.get("songName")
        return self._music.get("title") or self._audio.get("songName") or None

    @property
    def media_artist(self) -> str | None:
        if self._use_audio:
            return self._audio.get("artistName") or None
        return self._music.get("artist") or self._audio.get("artistName") or None

    @property
    def media_album_name(self) -> str | None:
        if self._use_audio:
            return self._audio.get("albumName") or None
        return self._music.get("album") or self._audio.get("albumName") or None

    @property
    def media_album_artist(self) -> str | None:
        return self._music.get("albumArtist") or None

    @property
    def media_track(self) -> int | None:
        return self._music.get("number") or None

    # Positions and durations are milliseconds (the app formats them with millSecondToTime).
    @property
    def media_duration(self) -> float | None:
        dur = self._info.get("duration") if self._external else self._state.get("duration")
        return dur / 1000 if dur else None

    @property
    def media_position(self) -> float | None:
        pos = self._info.get("currentPosition") if self._external else self._state.get("position")
        return pos / 1000 if pos is not None else None

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
        return {
            LOOP_REPEAT_ALL: RepeatMode.ALL,
            LOOP_REPEAT_ONE: RepeatMode.ONE,
            LOOP_SHUFFLE: RepeatMode.ALL,
            LOOP_PLAY_ONCE: RepeatMode.OFF,
        }.get(self._state.get("loopModel"), RepeatMode.ALL)

    @property
    def shuffle(self) -> bool:
        return self._state.get("loopModel") == LOOP_SHUFFLE

    @property
    def source_list(self) -> list[str]:
        return [i["name"] for i in self.coordinator.io["inputs"]]

    @property
    def source(self) -> str | None:
        return self._selected(self.coordinator.io["inputs"])

    # ---- cover ---------------------------------------------------------
    @property
    def _cover_url(self) -> str | None:
        return self.coordinator.api.cover_url(self._music, None if self._music else self._audio)

    @property
    def media_image_hash(self) -> str | None:
        url = self._cover_url
        return hashlib.md5(url.encode()).hexdigest() if url else None

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        url = self._cover_url
        result = await self.coordinator.api.fetch_image(url) if url else None
        return result if result else (None, None)

    # ---- attributes for the card and automations ------------------------
    @property
    def extra_state_attributes(self) -> dict:
        io = self.coordinator.io
        music, audio, out = self._music, self._audio, self._output
        audio_rate = audio.get("audioSampleRate")
        out_rate = out.get("outPutSampleRate")
        state = self._state

        def flag(has: str, active: str) -> bool | None:
            # None when the device has no such block (the app hides the icon).
            return bool(state.get(active, True)) if state.get(has) else None

        return {
            "input": self._selected(io["inputs"]),
            "input_list": [i["name"] for i in io["inputs"]],
            "output": self._selected(io["outputs"]),
            "output_list": [i["name"] for i in io["outputs"]],
            "loop_mode": LOOP_NAMES.get(self._state.get("loopModel"), "repeat_all"),
            "vu_mode": self._state.get("vuDisplayMode"),
            "spectrum_mode": self._state.get("spDisplayMode"),
            "app_list": [a["name"] for a in self.coordinator.apps],
            "app": self.coordinator.last_app,
            "power_list": [p["name"] for p in self.coordinator.power_options],
            "codec": music.get("codec") or audio.get("audioDecodec"),
            "sample_rate": music.get("sampleRate") or (f"{audio_rate / 1000:g} kHz" if audio_rate else None),
            "bits": music.get("bits") or audio.get("audioBitsPerSample") or None,
            "output_format": " · ".join(
                str(x)
                for x in (
                    out.get("outPutDecodec"),
                    f"{out_rate / 1000:g} kHz" if out_rate else None,
                    f"{out['outPutBits']}bit" if out.get("outPutBits") else None,
                )
                if x
            )
            or None,
            "output_codec": out.get("outPutDecodec") or None,
            "output_rate": f"{out_rate / 1000:g} kHz" if out_rate else None,
            "output_bits": out.get("outPutBits") or None,
            "channels": music.get("channels") or audio.get("audioChannels") or None,
            "bitrate": music.get("bitrate") or None,
            "source_name": self._info.get("playTypeSubtitle") or None,
            "dsp": flag("hasDspSetting", "dspActive"),
            "eq": flag("hasEQSetting", "eqActive"),
            "sub": flag("hasSubSetting", "subActive"),
            "volume_display": self._volume.get("display"),
            "model": self._entry.data.get(CONF_MODEL),
            "host": self.coordinator.api.host,
        }

    # ---- actions -------------------------------------------------------
    async def _refresh(self) -> None:
        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        if self.state != MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            await self._refresh()

    async def async_media_pause(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            await self._refresh()

    async def async_media_play_pause(self) -> None:
        await self.coordinator.api.play_pause()
        await self._refresh()

    async def async_media_next_track(self) -> None:
        await self.coordinator.api.next_track()
        await self._refresh()

    async def async_media_previous_track(self) -> None:
        await self.coordinator.api.previous_track()
        await self._refresh()

    async def async_media_seek(self, position: float) -> None:
        await self.coordinator.api.seek(int(position * 1000))
        await self._refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        # Same as the app: value = slider step * mMargin, slider max = maxVolume / mMargin.
        mx = self._volume.get("maxVolume") or 100
        step = self._volume.get("mMargin") or 1
        value = round(volume * mx / step) * step
        await self.coordinator.api.set_volume(max(0, min(mx, value)))
        await self._refresh()

    async def async_volume_up(self) -> None:
        await self.coordinator.api.key("VolumeUp")
        await self._refresh()

    async def async_volume_down(self) -> None:
        await self.coordinator.api.key("VolumeDown")
        await self._refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        if bool(self.is_volume_muted) != mute:
            await self.coordinator.api.key("Mute")
            await self._refresh()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        await self.coordinator.api.set_loop(REPEAT_TO_LOOP[repeat])
        await self._refresh()

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self.coordinator.api.set_loop(LOOP_SHUFFLE if shuffle else LOOP_REPEAT_ALL)
        await self._refresh()

    async def async_select_source(self, source: str) -> None:
        for item in self.coordinator.io["inputs"]:
            if item["name"] == source:
                await self.coordinator.api.set_input(item["tag"], item["index"])
                await self._refresh()
                return
