"""Screen mirroring: the Eversolo app's "remote screen" (a scrcpy-style stream).

Protocol, from RemoteScreenActivity / Scrcpy / ScrcpyApi / VideoPacket in the app:

1. GET :9529/ZidooControlCenter/setcastmode?mode=1&version=1
   -> {"port": n, "ip": "...", "videoWidth": w, "videoHeight": h, "isShowMenu": bool}
2. TCP connect to ip:port. The device sends packets [int32 length][payload], payload =
   [type: 1 = video][flag: 0 frame, 1 key frame, 2 config (SPS+PPS), 4 end][int64 pts][H.264 Annex-B].
3. The client writes touches on the same socket as 16 bytes: int32 action (0 down, 1 up,
   2 move), int32 button state, int32 x, int32 y, in video pixels (big endian).
4. GET :9529/ZidooControlCenter/setcastmode?mode=0&port=n stops it.

Home Assistant relays the stream to the card over its websocket, so it works wherever
the HA frontend works (including through a reverse proxy).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import struct
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .api import EversoloApi, EversoloError

_LOGGER = logging.getLogger(__name__)

TYPE_VIDEO = 1
FLAG_FRAME, FLAG_KEY, FLAG_CONFIG, FLAG_END = 0, 1, 2, 4
ACTION_DOWN, ACTION_UP, ACTION_MOVE = 0, 1, 2
STOP_GRACE_SECONDS = 15  # keep the stream open briefly when the card is re-rendered
MAX_GOP_FRAMES = 600  # frames kept since the last key frame, for viewers that join late
MAX_PACKET = 8 * 1024 * 1024

Listener = Callable[[dict[str, Any]], None]


class MirrorSession:
    """One stream per device, shared by every open card."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi) -> None:
        self.hass = hass
        self.api = api
        self._listeners: set[Listener] = set()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._stop_handle: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()
        self.port: int | None = None
        self.width = 0
        self.height = 0
        self._config: bytes | None = None
        self._gop: list[tuple[bool, bytes]] = []

    # ---- viewers ---------------------------------------------------------
    async def async_subscribe(self, listener: Listener) -> Callable[[], None]:
        if self._stop_handle:
            self._stop_handle.cancel()
            self._stop_handle = None
        self._listeners.add(listener)
        try:
            await self._async_ensure_running()
        except Exception:
            self._listeners.discard(listener)
            raise

        @callback
        def unsubscribe() -> None:
            self._listeners.discard(listener)
            if not self._listeners and self._stop_handle is None:
                self._stop_handle = self.hass.loop.call_later(
                    STOP_GRACE_SECONDS, lambda: self.hass.async_create_task(self.async_stop())
                )

        return unsubscribe

    @callback
    def replay(self, listener: Listener) -> None:
        """Late joiners get the codec config and the frames since the last key frame."""
        if self._config is not None:
            listener(self._config_message())
            for key, data in list(self._gop):
                listener(_frame_message(key, data))

    def _broadcast(self, message: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(message)
            except Exception:  # noqa: BLE001 - one broken viewer must not stop the others
                _LOGGER.debug("Mirror listener failed", exc_info=True)

    def _config_message(self) -> dict[str, Any]:
        return {
            "type": "config",
            "width": self.width,
            "height": self.height,
            "data": base64.b64encode(self._config or b"").decode(),
        }

    # ---- stream ----------------------------------------------------------
    async def _async_ensure_running(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            resp = await self.api.request("/ZidooControlCenter/setcastmode?mode=1&version=1", timeout=10)
            if not isinstance(resp, dict) or "port" not in resp:
                raise EversoloError(f"screen mirroring was not started: {resp!r}")
            self.port = int(resp["port"])
            self.width = int(resp.get("videoWidth") or 0)
            self.height = int(resp.get("videoHeight") or 0)
            host = resp.get("ip") or self.api.host
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(host, self.port), timeout=10
                )
            except (OSError, asyncio.TimeoutError):
                if host == self.api.host:
                    raise
                # The device may report an address HA cannot reach; fall back to the configured one.
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.api.host, self.port), timeout=10
                )
            self._config = None
            self._gop = []
            self._task = self.hass.async_create_background_task(self._async_read_loop(), "eversolo mirror")

    async def _async_read_loop(self) -> None:
        reader = self._reader
        assert reader is not None
        try:
            while True:
                length = int.from_bytes(await reader.readexactly(4), "big", signed=True)
                if length <= 0 or length > MAX_PACKET:
                    continue
                packet = await reader.readexactly(length)
                if len(packet) < 10 or packet[0] != TYPE_VIDEO:
                    continue
                flag, data = packet[1], packet[10:]
                if flag == FLAG_CONFIG:
                    self._config = data
                    self._gop = []
                    self._broadcast(self._config_message())
                elif flag == FLAG_END:
                    break
                else:
                    key = flag == FLAG_KEY
                    if key:
                        self._gop = []
                    if len(self._gop) < MAX_GOP_FRAMES:
                        self._gop.append((key, data))
                    self._broadcast(_frame_message(key, data))
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as err:
            _LOGGER.debug("Mirror stream closed: %s", err)
        finally:
            self._broadcast({"type": "ended"})
            await self._async_close_socket()

    async def _async_close_socket(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def async_stop(self) -> None:
        self._stop_handle = None
        if self._listeners:
            return
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
        await self._async_close_socket()
        if self.port is not None:
            try:
                await self.api.request(f"/ZidooControlCenter/setcastmode?mode=0&port={self.port}", raw=True)
            except EversoloError as err:
                _LOGGER.debug("Could not stop mirroring: %s", err)
            self.port = None

    async def async_shutdown(self) -> None:
        self._listeners.clear()
        if self._stop_handle:
            self._stop_handle.cancel()
        await self.async_stop()

    # ---- input -----------------------------------------------------------
    async def async_touch(self, action: int, x: int, y: int) -> None:
        if not self._writer:
            return
        x = max(0, min(int(x), max(0, self.width - 1)))
        y = max(0, min(int(y), max(0, self.height - 1)))
        self._writer.write(struct.pack(">iiii", int(action), 0, x, y))
        await self._writer.drain()


def _frame_message(key: bool, data: bytes) -> dict[str, Any]:
    return {"type": "frame", "key": key, "data": base64.b64encode(data).decode()}
