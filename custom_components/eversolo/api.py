"""HTTP client for the Eversolo control API (port 9529, plain GET, JSON).

Every call here mirrors a call made by the Eversolo Controller app; the
source class is named next to each method (see docs/protocol.md).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

import aiohttp

from homeassistant.exceptions import HomeAssistantError

from .const import APP_STATUS_OPENABLE, DEFAULT_PORT, POWER_TAG_TIMER, SPECTRUM_OPEN_TYPE, VU_OPEN_TYPE

_LOGGER = logging.getLogger(__name__)

MUSIC = "/ZidooMusicControl/v2"
CTRL = "/ZidooControlCenter"


class EversoloError(HomeAssistantError):
    """Generic API error.

    A HomeAssistantError, so a failed action shows its message in the UI
    instead of "unknown error" with a traceback in the log.
    """


class EversoloConnectionError(EversoloError):
    """The device did not answer."""


def _q(value: Any) -> str:
    return urllib.parse.quote(str(value), safe="")


def _items(node: Any) -> list[dict]:
    """Return the list of dict items from a response of unknown envelope shape."""
    if isinstance(node, list):
        return [i for i in node if isinstance(i, dict)]
    if isinstance(node, dict):
        for key in ("data", "array", "list", "items"):
            if key in node:
                return _items(node[key])
    return []


def _entry(item: dict, index: int, selected: bool) -> dict:
    tag = str(item.get("tag", ""))
    return {"tag": tag, "name": str(item.get("name") or tag), "index": index, "selected": selected}


def parse_io(data: Any) -> dict[str, list[dict]]:
    """Split getInputAndOutputList (SourceInBean) into inputs and outputs.

    The app marks the current entry by its position: inputIndex / outputIndex.
    """
    result: dict[str, list[dict]] = {"inputs": [], "outputs": []}
    if not isinstance(data, dict):
        return result
    in_idx = data.get("inputIndex")
    out_idx = data.get("outputIndex")
    for i, item in enumerate(_items(data.get("inputData"))):
        result["inputs"].append(_entry(item, i, i == in_idx))
    for i, item in enumerate(_items(data.get("outputData"))):
        result["outputs"].append(_entry(item, i, i == out_idx))
    return result


def parse_power_options(data: Any) -> list[dict]:
    """getPowerOption -> [{name, tag}], without the timer entry (it needs its own dialog)."""
    out = []
    for item in _items(data):
        tag = item.get("tag")
        if not tag or tag == POWER_TAG_TIMER:
            continue
        out.append({"tag": str(tag), "name": str(item.get("name") or tag)})
    return out


def parse_apps(data: Any) -> list[dict]:
    """getStreamMediaAppList -> installed apps [{name, package}] (appStatus 0 or 2)."""
    out = []
    for item in _items(data):
        package = item.get("packageName")
        if not package or item.get("appStatus", 0) not in APP_STATUS_OPENABLE:
            continue
        out.append({"package": str(package), "name": str(item.get("title") or package)})
    return out


class EversoloApi:
    """Thin async wrapper around the device HTTP API."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int = DEFAULT_PORT) -> None:
        self._session = session
        self.host = host
        self.port = port
        self.base = f"http://{host}:{port}"

    async def request(self, path: str, *, raw: bool = False, timeout: float = 5) -> Any:
        url = self.base + path
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise EversoloError(f"HTTP {resp.status} for {path}")
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("%s: %s", url, err)
            raise EversoloConnectionError(f"The player at {self.host} does not answer") from err
        if raw:
            return text
        try:
            return json.loads(text)
        except ValueError:
            return text

    # ---- pairing (ConnectionTool) ---------------------------------------
    async def connect(self, name: str, client_uuid: str, ask_authority: bool) -> dict:
        query = urllib.parse.urlencode(
            {"name": name, "uuid": client_uuid, "tag": int(ask_authority), "type": 1}
        )
        # tag=1 blocks until the user answers the prompt on the device screen.
        timeout = 30 if ask_authority else 5
        resp = await self.request(f"{CTRL}/connect?{query}", timeout=timeout)
        return resp if isinstance(resp, dict) else {}

    # ---- reads -----------------------------------------------------------
    async def get_state(self) -> dict:
        """MusicManager URL_GET_STATE -> MusicState."""
        resp = await self.request(f"{MUSIC}/getState")
        if not isinstance(resp, dict):
            raise EversoloError("unexpected getState response")
        return resp

    async def get_io(self) -> dict[str, list[dict]]:
        """SourceInOutputFragment, polled every 2 s by the app."""
        return parse_io(await self.request(f"{MUSIC}/getInputAndOutputList?isLight=true"))

    async def get_power_options(self) -> list[dict]:
        """DevicePowerDialog menu, labels come from the device in its own language."""
        return parse_power_options(await self.request(f"{MUSIC}/getPowerOption"))

    async def get_apps(self) -> list[dict]:
        """HomeFragment / ModuleFragment app list."""
        return parse_apps(
            await self.request(f"{MUSIC}/getStreamMediaAppList?start=0&count=100&showMusicApp=true&sort=4")
        )

    def cover_url(self, music: dict | None, audio: dict | None = None) -> str | None:
        """Album art the way RotateFragment loads it.

        playingMusic.albumArt is a full URL when set; otherwise the app asks
        getImage for the track id (MusicImageLoader.music(): type=4, target=16).
        Sources outside the library report everSoloPlayAudioInfo.albumUrl.
        """
        music = music or {}
        art = music.get("albumArt") or music.get("albumArtBig")
        if art:
            return art if art.startswith("http") else self.base + art
        if music.get("id"):
            return (
                f"{self.base}{MUSIC}/getImage?id={_q(music['id'])}"
                f"&musicType={_q(music.get('type', 0))}&type=4&target=16"
            )
        url = (audio or {}).get("albumUrl")
        if url:
            return url if url.startswith("http") else self.base + url
        return None

    async def fetch_image(self, url: str) -> tuple[bytes, str] | None:
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read(), resp.headers.get("Content-Type", "image/jpeg")
        except (aiohttp.ClientError, TimeoutError):
            return None

    # ---- transport (MusicManager) ---------------------------------------
    async def play_pause(self) -> None:
        await self.request(f"{MUSIC}/playOrPause", raw=True)

    async def next_track(self) -> None:
        await self.request(f"{MUSIC}/playNext", raw=True)

    async def previous_track(self) -> None:
        await self.request(f"{MUSIC}/playLast", raw=True)

    async def seek(self, position_ms: int) -> None:
        await self.request(f"{MUSIC}/seekTo?time={int(position_ms)}", raw=True)

    async def set_loop(self, mode: int) -> None:
        await self.request(f"{MUSIC}/setLoopMode?loop={int(mode)}", raw=True)

    async def set_volume(self, value: int) -> None:
        """Raw device units, 0..volumeData.maxVolume in steps of volumeData.mMargin."""
        await self.request(f"{MUSIC}/setDevicesVolume?volume={int(value)}", raw=True)

    async def key(self, name: str) -> None:
        """Remote key, e.g. Mute, VolumeUp, VolumeDown."""
        await self.request(f"{CTRL}/RemoteControl/sendkey?key=Key.{_q(name)}", raw=True)

    # ---- display, sources, power ----------------------------------------
    async def vu_next(self) -> None:
        """DetailsFragment vu_change: next VU display mode."""
        await self.request(f"{MUSIC}/changVUDisplay?openType={VU_OPEN_TYPE}", raw=True)

    async def spectrum_next(self) -> None:
        """DetailsFragment sp_change: next spectrum display mode."""
        await self.request(f"{MUSIC}/changVUDisplay?openType={SPECTRUM_OPEN_TYPE}", raw=True)

    async def set_input(self, tag: str, index: int) -> None:
        await self.request(f"{MUSIC}/setInputList?tag={_q(tag)}&index={int(index)}&isLight=true", raw=True)

    async def set_output(self, tag: str, index: int) -> None:
        await self.request(f"{MUSIC}/setOutInputList?tag={_q(tag)}&index={int(index)}&isLight=true", raw=True)

    async def open_app(self, package: str) -> None:
        """HomeStreamFragment.openApp: launch a streaming app on the device screen."""
        await self.request(f"{CTRL}/Apps/openApp?packageName={_q(package)}", raw=True)

    # ---- brightness (SystemSettings/displaySettings) -----------------------
    async def get_brightness(self, kind: str) -> dict | None:
        """kind: "Screen" or "Knob" -> {currentValue, minValue, maxValue}; None when the model has none."""
        resp = await self.request(f"/SystemSettings/displaySettings/get{kind}Brightness")
        if not isinstance(resp, dict) or resp.get("status") != 200 or resp.get("currentValue") is None:
            return None
        return {
            "value": int(resp["currentValue"]),
            "min": int(resp.get("minValue") or 0),
            "max": int(resp.get("maxValue") or 100),
        }

    async def set_brightness(self, kind: str, value: int) -> None:
        await self.request(f"/SystemSettings/displaySettings/set{kind}Brightness?index={int(value)}", raw=True)

    # ---- DSP / EQ per source (DspPresenter) -------------------------------
    async def get_dsp_source(self, is_dsp: bool) -> dict | None:
        """The DSP (analog outputs) or EQ (digital outputs) assignment of the current source:
        {id, eqId, name, enable, sourceType, configName}. None when it does not apply right now."""
        resp = await self.request(f"{MUSIC}/getDSPCurrentSource?isDSP={str(is_dsp).lower()}")
        source = resp.get("dspSource") if isinstance(resp, dict) else None
        return source if isinstance(source, dict) and "id" in source else None

    async def get_dsp_configs(self, is_dsp: bool) -> list[dict]:
        resp = await self.request(
            f"{MUSIC}/getDSPConfigList?limit=50&offset=0&isDSP={str(is_dsp).lower()}&isPEQDrc=false"
        )
        configs = resp.get("dspConfig") if isinstance(resp, dict) else None
        return [
            {"id": c["id"], "name": str(c.get("name") or c["id"])}
            for c in (configs or [])
            if isinstance(c, dict) and "id" in c
        ]

    async def set_dsp_source(self, source: dict, enable: bool, config_id: int) -> None:
        """Same call as the app's DSP page: switch processing on/off and pick the config for a source."""
        await self.request(
            f"{MUSIC}/setDSPSource?id={_q(source['id'])}&sourceType={_q(source.get('sourceType', ''))}"
            f"&enable={str(bool(enable)).lower()}&eqId={_q(config_id)}",
            raw=True,
        )

    async def power(self, tag: str) -> None:
        """DevicePowerDialog item: tag from getPowerOption."""
        await self.request(f"{MUSIC}/setPowerOption?tag={_q(tag)}", raw=True)
