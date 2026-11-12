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
from homeassistant.util import dt as dt_util

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
POWER_OFF = MediaPlayerEntityFeature.TURN_OFF
POWER_ON = MediaPlayerEntityFeature.TURN_ON
OTHER = (
    MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

# How far the reported position may drift from the extrapolated one before it is re-stamped.
POSITION_TOLERANCE_SECONDS = 1.5

REPEAT_TO_LOOP = {RepeatMode.ALL: LOOP_REPEAT_ALL, RepeatMode.ONE: LOOP_REPEAT_ONE, RepeatMode.OFF: LOOP_PLAY_ONCE}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EversoloCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EversoloPlayer(coordinator, entry)])


class EversoloPlayer(EversoloEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_media_image_remotely_accessible = False

    def __init__(self, coordinator: EversoloCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "player")
        self._pos: float | None = None
        self._pos_at: datetime | None = None
        self._pos_key: tuple | None = None
        self._pos_raw: float | None = None
        self._pos_synced: datetime | None = None

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
    # ---- power -----------------------------------------------------------
    @property
    def _power(self):
        return self.coordinator.power

    @property
    def available(self) -> bool:
        # With a known MAC the player can be woken, so it shows as "off" instead of unavailable.
        return self.coordinator.last_update_success or bool(self._power and self._power.can_wake)

    async def async_turn_on(self) -> None:
        await self._power.async_turn_on()

    async def async_turn_off(self) -> None:
        await self._power.async_turn_off()

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        power = self._power
        if power:
            base = POWER_OFF | (POWER_ON if power.can_wake else MediaPlayerEntityFeature(0))
            if not self.coordinator.last_update_success or not power.is_on:
                return base
        else:
            base = MediaPlayerEntityFeature(0)
        return base | self._playback_features

    @property
    def _playback_features(self) -> MediaPlayerEntityFeature:
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
        power = self._power
        if power and not power.is_on:
            return MediaPlayerState.OFF
        if not self.coordinator.last_update_success:
            return MediaPlayerState.IDLE  # woken, still booting
        return self._play_state

    @property
    def _play_state(self) -> MediaPlayerState:
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
    def _raw_position(self) -> float | None:
        pos = self._info.get("currentPosition") if self._external else self._state.get("position")
        return pos / 1000 if pos is not None else None

    def _sync_position(self) -> None:
        """Keep one (position, time) pair for as long as the player follows it.

        The frontend extrapolates the position from this pair while playing. Stamping every
        2 s poll would change the entity's attributes each time (a state write and a recorder
        row every 2 s, even when paused), so the pair is replaced only when the state or the
        track changes or the reported position leaves the expected one (seek, stall).
        """
        stamp = self.coordinator.last_update_success_time
        if stamp is None or stamp is self._pos_synced:
            return
        self._pos_synced = stamp
        raw, state = self._raw_position, self.state
        key = (state, self.media_title, self.media_duration)
        last_raw, self._pos_raw = self._pos_raw, raw
        if raw is not None and self._pos is not None and self._pos_at is not None and key == self._pos_key:
            if raw == last_raw:
                # Not moving although "playing": a live input (ARC, optical, ...) or a stall.
                return
            expected = self._pos
            if state == MediaPlayerState.PLAYING:
                expected += (stamp - self._pos_at).total_seconds()
            if abs(raw - expected) <= POSITION_TOLERANCE_SECONDS:
                return
        self._pos, self._pos_at, self._pos_key = raw, stamp, key

    @property
    def media_position(self) -> float | None:
        self._sync_position()
        return self._pos

    @property
    def media_position_updated_at(self) -> datetime | None:
        self._sync_position()
        return self._pos_at if self._pos is not None else None

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
            # Real devices put the file format in playingMusic.extension ("FLAC").
            "codec": music.get("codec") or music.get("extension") or audio.get("audioDecodec") or None,
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
            # Streaming services name themselves in playingMusic.streamId ("qobuz");
            # playTypeSubtitle is generic ("LOCAL") for everything in the library player.
            "source_name": music.get("streamId") or self._info.get("playTypeSubtitle") or None,
            "dsp": flag("hasDspSetting", "dspActive"),
            "eq": flag("hasEQSetting", "eqActive"),
            "sub": flag("hasSubSetting", "subActive"),
            "volume_display": self._volume.get("display"),
            "model": self._entry.data.get(CONF_MODEL),
            "host": self.coordinator.api.host,
        }

    # ---- actions -------------------------------------------------------
    async def _refresh(self) -> None:
        self.coordinator.confirm_later()

    def _apply_playing(self, playing: bool) -> None:
        """Flip play/pause in the UI at once: the device takes a moment to report it."""
        if self._external:
            self.coordinator.apply(info={"playStatus": 1 if playing else 2})
        else:
            # Keep the shown position where it is now, then switch state.
            pos = self.media_position
            changes = {"state": STATE_PLAYING if playing else STATE_PAUSED}
            if pos is not None and self.state == MediaPlayerState.PLAYING and self.media_position_updated_at:
                elapsed = (dt_util.utcnow() - self.media_position_updated_at).total_seconds()
                changes["position"] = int((pos + max(0.0, elapsed)) * 1000)
            self.coordinator.apply(state=changes)

    async def _fresh_state(self) -> None:
        """The player only has toggles for play/pause and mute, so "pause" on a stale state
        could start playback. Read it right before deciding (unless a command was just sent
        and the optimistic state is newer than what the player reports)."""
        if not self.coordinator.command_pending:
            await self.coordinator.async_refresh()

    async def async_media_play(self) -> None:
        await self._fresh_state()
        if self.state != MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            self._apply_playing(True)

    async def async_media_pause(self) -> None:
        await self._fresh_state()
        if self.state == MediaPlayerState.PLAYING:
            await self.coordinator.api.play_pause()
            self._apply_playing(False)

    async def async_media_play_pause(self) -> None:
        playing = self.state == MediaPlayerState.PLAYING
        await self.coordinator.api.play_pause()
        self._apply_playing(not playing)

    async def async_media_next_track(self) -> None:
        await self.coordinator.api.next_track()
        await self._refresh()

    async def async_media_previous_track(self) -> None:
        await self.coordinator.api.previous_track()
        await self._refresh()

    async def async_media_seek(self, position: float) -> None:
        ms = int(position * 1000)
        await self.coordinator.api.seek(ms)
        if self._external:
            self.coordinator.apply(info={"currentPosition": ms})
        else:
            self.coordinator.apply(state={"position": ms})

    async def async_set_volume_level(self, volume: float) -> None:
        # Same as the app: value = slider step * mMargin, slider max = maxVolume / mMargin.
        mx = self._volume.get("maxVolume") or 100
        step = self._volume.get("mMargin") or 1
        value = round(volume * mx / step) * step
        value = max(0, min(mx, value))
        await self.coordinator.api.set_volume(value)
        self.coordinator.apply(volume={"currenttVolume": value})

    async def async_volume_up(self) -> None:
        await self.coordinator.api.key("VolumeUp")
        await self._refresh()

    async def async_volume_down(self) -> None:
        await self.coordinator.api.key("VolumeDown")
        await self._refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        await self._fresh_state()
        if bool(self.is_volume_muted) != mute:
            await self.coordinator.api.key("Mute")
            self.coordinator.apply(volume={"isMute": mute})

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        await self.coordinator.api.set_loop(REPEAT_TO_LOOP[repeat])
        self.coordinator.apply(state={"loopModel": REPEAT_TO_LOOP[repeat]})

    async def async_set_shuffle(self, shuffle: bool) -> None:
        mode = LOOP_SHUFFLE if shuffle else LOOP_REPEAT_ALL
        await self.coordinator.api.set_loop(mode)
        self.coordinator.apply(state={"loopModel": mode})

    async def async_select_source(self, source: str) -> None:
        for item in self.coordinator.io["inputs"]:
            if item["name"] == source:
                await self.coordinator.api.set_input(item["tag"], item["index"])
                self.coordinator.select_io("inputs", item["index"])
                return
