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

Flow control: that websocket is shared with the rest of the frontend, and Home Assistant
drops a connection whose send queue stays long. So every viewer acknowledges the frames it
received; a viewer that falls behind gets no more frames until it has caught up, and then
continues from the last key frame (config + the frames since it), like a viewer that joins late.
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
MAX_UNACKED_FRAMES = 60  # about 2 s of video in flight: beyond this the viewer is paused
RESUME_UNACKED_FRAMES = 10  # a paused viewer continues once it is this close again

Listener = Callable[[dict[str, Any]], None]


class Viewer:
    """One open card: where to send, and how far it has got."""

    _next_id = 0

    def __init__(self, send: Listener) -> None:
        Viewer._next_id += 1
        self.id = Viewer._next_id
        self.send = send
        self.sent = 0
        self.acked: int | None = None  # None: a card without acknowledgements (older version)
        self.synced = False
        self.burst_end = 0  # frame count after the last catch-up burst

    @property
    def unacked(self) -> int:
        return 0 if self.acked is None else self.sent - self.acked

    @property
    def behind(self) -> int:
        """Live frames in flight. The catch-up burst itself does not count: it may be longer
        than the limit, and counting it would pause the viewer again right after resuming."""
        return 0 if self.acked is None else self.sent - max(self.acked, self.burst_end)


class MirrorSession:
    """One stream per device, shared by every open card."""

    def __init__(self, hass: HomeAssistant, api: EversoloApi) -> None:
        self.hass = hass
        self.api = api
        self._viewers: dict[int, Viewer] = {}
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
        self._gop_complete = True

    # ---- viewers ---------------------------------------------------------
    async def async_subscribe(self, listener: Listener) -> tuple[Viewer, Callable[[], None]]:
        """Start the stream if needed. Call start(viewer) once the caller is ready for messages."""
        if self._stop_handle:
            self._stop_handle.cancel()
            self._stop_handle = None
        viewer = Viewer(listener)
        try:
            await self._async_ensure_running()
        except Exception:
            self._schedule_stop()
            raise

        @callback
        def unsubscribe() -> None:
            self._viewers.pop(viewer.id, None)
            self._schedule_stop()

        return viewer, unsubscribe

    @callback
    def _schedule_stop(self) -> None:
        if not self._viewers and self._stop_handle is None:
            self._stop_handle = self.hass.loop.call_later(
                STOP_GRACE_SECONDS, lambda: self.hass.async_create_task(self.async_stop())
            )

    @callback
    def start(self, viewer: Viewer) -> None:
        """Begin sending to a viewer: the picture so far (config + frames since the key frame), then live."""
        if self._stop_handle:
            self._stop_handle.cancel()
            self._stop_handle = None
        self._viewers[viewer.id] = viewer
        self._sync(viewer)

    @callback
    def ack(self, viewer_id: int, received: int) -> None:
        """The card reports how many frames it has received in total."""
        viewer = self._viewers.get(viewer_id)
        if viewer is None:
            return
        viewer.acked = max(viewer.acked or 0, min(int(received), viewer.sent))
        if not viewer.synced and viewer.unacked <= RESUME_UNACKED_FRAMES:
            self._sync(viewer)

    def _send(self, viewer: Viewer, message: dict[str, Any]) -> None:
        try:
            viewer.send(message)
        except Exception:  # noqa: BLE001 - one broken viewer must not stop the others
            _LOGGER.debug("Mirror viewer failed", exc_info=True)

    def _sync(self, viewer: Viewer) -> None:
        """Send config and the frames since the last key frame, if they are all still there."""
        if self._config is None or not self._gop or not self._gop_complete:
            return  # nothing to show yet; the next key frame syncs the viewer
        self._send(viewer, self._config_message(viewer))
        for key, data in self._gop:
            self._send(viewer, _frame_message(key, data))
        viewer.sent += len(self._gop)
        viewer.burst_end = viewer.sent
        viewer.synced = True

    def _deliver(self, key: bool, data: bytes) -> None:
        """A new frame (already appended to the GOP) for every viewer."""
        message = None
        for viewer in list(self._viewers.values()):
            if viewer.synced and viewer.behind > MAX_UNACKED_FRAMES:
                viewer.synced = False  # fell behind: pause, then continue from a key frame
            if not viewer.synced:
                if viewer.unacked <= RESUME_UNACKED_FRAMES:
                    self._sync(viewer)
                continue
            message = message or _frame_message(key, data)
            self._send(viewer, message)
            viewer.sent += 1

    def _broadcast(self, message: dict[str, Any]) -> None:
        for viewer in list(self._viewers.values()):
            self._send(viewer, message)

    def _config_message(self, viewer: Viewer) -> dict[str, Any]:
        return {
            "type": "config",
            "viewer": viewer.id,
            "width": self.width,
            "height": self.height,
            "data": base64.b64encode(self._config or b"").decode(),
        }

    # ---- stream ----------------------------------------------------------
    async def _async_ensure_running(self) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                return
            if self.port is not None:
                # The previous stream ended on its own; tell the player it is closed before starting anew.
                old, self.port = self.port, None
                try:
                    await self.api.request(f"/ZidooControlCenter/setcastmode?mode=0&port={old}", raw=True)
                except EversoloError:
                    pass
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
            self._gop, self._gop_complete = [], True
            self._task = self.hass.async_create_background_task(self._async_read_loop(), "eversolo mirror")

    async def _async_read_loop(self) -> None:
        reader = self._reader
        assert reader is not None
        try:
            while True:
                length = int.from_bytes(await reader.readexactly(4), "big", signed=True)
                if length <= 0 or length > MAX_PACKET:
                    # Out of step with the stream: nothing after this can be trusted.
                    _LOGGER.debug("Mirror stream: bad packet length %s", length)
                    break
                packet = await reader.readexactly(length)
                if len(packet) < 10 or packet[0] != TYPE_VIDEO:
                    continue
                flag, data = packet[1], packet[10:]
                if flag == FLAG_CONFIG:
                    self._config = data
                    self._gop, self._gop_complete = [], True
                    for viewer in self._viewers.values():
                        viewer.synced = False  # new stream parameters: start again at the next key frame
                elif flag == FLAG_END:
                    break
                else:
                    key = flag == FLAG_KEY
                    if key:
                        self._gop, self._gop_complete = [], True
                    if len(self._gop) < MAX_GOP_FRAMES:
                        self._gop.append((key, data))
                    else:
                        # Too long without a key frame to keep it all: late viewers wait for the next one.
                        self._gop_complete = False
                    self._deliver(key, data)
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
        # Under the lock, so a card that opens right now starts a new stream only after this
        # one is fully closed (and this cannot close the new one by mistake).
        async with self._lock:
            if self._viewers:
                return
            task, self._task = self._task, None
            port, self.port = self.port, None
            if task and not task.done():
                task.cancel()
            await self._async_close_socket()
            if port is not None:
                try:
                    await self.api.request(f"/ZidooControlCenter/setcastmode?mode=0&port={port}", raw=True)
                except EversoloError as err:
                    _LOGGER.debug("Could not stop mirroring: %s", err)

    async def async_shutdown(self) -> None:
        self._viewers.clear()
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
