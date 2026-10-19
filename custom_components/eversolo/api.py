"""HTTP client for the Eversolo control API (port 9529, plain GET, JSON)."""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

import aiohttp

from .const import CONF_CLIENT_UUID, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

MUSIC = "/ZidooMusicControl/v2"
CTRL = "/ZidooControlCenter"
FUNC = "/SystemSettings/functionSettings"


class EversoloError(Exception):
    """Generic API error."""


class EversoloConnectionError(EversoloError):
    """The device did not answer."""


def _items(node: Any) -> list[dict]:
    """Return the list of dict items from a response of unknown envelope shape."""
    if isinstance(node, list):
        return [i for i in node if isinstance(i, dict)]
    if isinstance(node, dict):
        for key in ("array", "data", "list", "items"):
            if key in node:
                return _items(node[key])
    return []


def _norm(item: dict) -> dict:
    tag = item.get("tag", item.get("id", item.get("name")))
    name = item.get("name") or item.get("title") or str(tag)
    selected = bool(
        item.get("isSelect")
        or item.get("isSelected")
        or item.get("selected")
        or item.get("checked")
    )
    return {"tag": str(tag), "name": str(name), "selected": selected}


def parse_io(data: Any) -> dict[str, list[dict]]:
    """Split getInputAndOutputList into inputs and outputs (best effort)."""
    result: dict[str, list[dict]] = {"inputs": [], "outputs": []}
    if isinstance(data, dict):
        for key, value in data.items():
            low = key.lower()
            if "output" in low or low == "out":
                result["outputs"] += [_norm(i) for i in _items(value)]
            elif "input" in low or "source" in low:
                result["inputs"] += [_norm(i) for i in _items(value)]
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type", item.get("direction", ""))).lower()
            bucket = "outputs" if "out" in kind else "inputs"
            result[bucket].append(_norm(item))
    return result


def parse_services(data: Any) -> list[dict]:
    return [_norm(i) for i in _items(data)]


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
            raise EversoloConnectionError(f"{url}: {err}") from err
        if raw:
            return text
        try:
            return json.loads(text)
        except ValueError:
            return text

    # ---- pairing -------------------------------------------------------
    async def connect(self, name: str, client_uuid: str, ask_authority: bool) -> dict:
        query = urllib.parse.urlencode(
            {"name": name, "uuid": client_uuid, "tag": int(ask_authority), "type": 1}
        )
        timeout = 30 if ask_authority else 5
        resp = await self.request(f"{CTRL}/connect?{query}", timeout=timeout)
        return resp if isinstance(resp, dict) else {}

    # ---- reads ---------------------------------------------------------
    async def get_state(self) -> dict:
        resp = await self.request(f"{MUSIC}/getState")
        if not isinstance(resp, dict):
            raise EversoloError("unexpected getState response")
        return resp

    async def get_io(self) -> dict[str, list[dict]]:
        return parse_io(await self.request(f"{MUSIC}/getInputAndOutputList?isLight=true"))

    async def get_services(self) -> list[dict]:
        return parse_services(await self.request(f"{MUSIC}/getSupportServer"))

    async def get_cover(self, music: dict) -> tuple[bytes, str] | None:
        art = music.get("albumArtBig") or music.get("albumArt")
        if not art:
            return None
        if art.startswith("http"):
            url = art
        else:
            url = self.base + MUSIC + "/getImage?content=" + urllib.parse.quote(art, safe="")
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read(), resp.headers.get("Content-Type", "image/jpeg")
        except (aiohttp.ClientError, TimeoutError):
            return None

    # ---- transport -----------------------------------------------------
    async def play_pause(self) -> None:
        await self.request(f"{MUSIC}/playOrPause", raw=True)

    async def next_track(self) -> None:
        await self.request(f"{MUSIC}/playNext", raw=True)

    async def previous_track(self) -> None:
        await self.request(f"{MUSIC}/playLast", raw=True)

    async def seek(self, value: int) -> None:
        await self.request(f"{MUSIC}/seekTo?time={int(value)}", raw=True)

    async def set_loop(self, mode: int) -> None:
        await self.request(f"{MUSIC}/setLoopMode?loop={int(mode)}", raw=True)

    async def set_volume(self, level: int) -> None:
        await self.request(f"{MUSIC}/setDevicesVolume?volume={int(level)}", raw=True)

    async def key(self, name: str) -> None:
        await self.request(f"{CTRL}/RemoteControl/sendkey?key=Key.{name}", raw=True)

    async def set_vu(self, open_type: int) -> None:
        await self.request(f"{MUSIC}/changVUDisplay?openType={int(open_type)}", raw=True)

    async def set_input(self, tag: str) -> None:
        await self.request(f"{MUSIC}/setInputList?tag={urllib.parse.quote(tag, safe='')}", raw=True)

    async def set_output(self, tag: str) -> None:
        await self.request(f"{MUSIC}/setOutInputList?tag={urllib.parse.quote(tag, safe='')}", raw=True)

    async def set_service(self, tag: str) -> None:
        await self.request(
            f"{MUSIC}/setDisplayMusicServerTag?parentTag={urllib.parse.quote(tag, safe='')}", raw=True
        )

    async def set_display(self, on: bool) -> None:
        # UNVERIFIED: front-panel display control endpoint, see README.
        await self.request(f"{FUNC}/setFrontBright?value={0 if not on else 3}", raw=True)
