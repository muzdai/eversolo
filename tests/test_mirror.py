"""MirrorSession against a fake Eversolo that speaks the app's remote-screen protocol."""
import asyncio
import json
import struct
import sys

sys.path[:0] = [sys.argv[1], sys.argv[2]]  # stubs, custom_components

from eversolo import mirror as mirror_mod
from eversolo.mirror import MirrorSession

STREAM = open(sys.argv[3], "rb").read()
OUT = sys.argv[4]


def split_nals(buf):
    """Annex-B -> list of NAL units, each with its 4-byte start code."""
    idx, i = [], 0
    while i < len(buf) - 3:
        if buf[i:i + 4] == b"\0\0\0\1":
            idx.append(i); i += 4
        elif buf[i:i + 3] == b"\0\0\1":
            idx.append(i); i += 3
        else:
            i += 1
    out = []
    for n, start in enumerate(idx):
        end = idx[n + 1] if n + 1 < len(idx) else len(buf)
        nal = buf[start:end]
        if nal[:3] == b"\0\0\1":
            nal = b"\0" + nal
        out.append(nal)
    return out


def device_packets():
    """Group NALs the way the device sends them: config (SPS+PPS), then one access unit per packet."""
    nals = split_nals(STREAM)
    config = b"".join(n for n in nals if n[4] & 0x1F in (7, 8))
    packets, pending = [(2, config)], b""
    for n in nals:
        t = n[4] & 0x1F
        if t in (7, 8):
            continue
        pending += n
        if t in (1, 5):
            packets.append((1 if t == 5 else 0, pending))
            pending = b""
    return packets


PACKETS = device_packets()
received = []


async def handle(reader, writer):
    for flag, data in PACKETS:
        payload = bytes([1, flag]) + struct.pack(">q", 0) + data
        writer.write(struct.pack(">i", len(payload)) + payload)
        await writer.drain()
    try:
        while True:
            received.append(struct.unpack(">iiii", await asyncio.wait_for(reader.readexactly(16), 2)))
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
        pass


class FakeApi:
    host = "127.0.0.1"

    def __init__(self, port):
        self.port, self.calls = port, []

    async def request(self, path, raw=False, timeout=5):
        self.calls.append(path)
        if "mode=1" in path:
            return {"port": self.port, "ip": "127.0.0.1", "videoWidth": 960, "videoHeight": 480, "isShowMenu": False}
        return "ok"


class FakeHass:
    def __init__(self):
        self.loop = asyncio.get_running_loop()

    def async_create_background_task(self, coro, name):
        return self.loop.create_task(coro)

    def async_create_task(self, coro):
        return self.loop.create_task(coro)


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    check.failed += not cond


check.failed = 0


async def main():
    mirror_mod.STOP_GRACE_SECONDS = 0.3
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    api = FakeApi(port)
    session = MirrorSession(FakeHass(), api)
    got = []
    viewer, unsub = await session.async_subscribe(got.append)
    session.start(viewer)
    await asyncio.sleep(0.8)
    check(api.calls[0] == "/ZidooControlCenter/setcastmode?mode=1&version=1", "starts with setcastmode mode=1")
    check(got and got[0]["type"] == "config" and got[0]["width"] == 960, "first message is config with size")
    frames = [m for m in got if m["type"] == "frame"]
    check(len(frames) == len(PACKETS) - 1, f"all frames relayed ({len(frames)})")
    check(frames[0]["key"] and sum(f["key"] for f in frames) == sum(1 for f, _ in PACKETS if f == 1), "key frames flagged")
    late = []
    session.start(mirror_mod.Viewer(late.append))
    session._viewers.popitem()
    check(late[0]["type"] == "config" and late[1]["key"] and len(late) <= 31, f"late joiner gets config + current GOP ({len(late) - 1} frames)")
    await session.async_touch(0, 100, 50)
    await session.async_touch(2, 2000, -5)
    await session.async_touch(1, 120, 60)
    await asyncio.sleep(0.3)
    check(received[:3] == [(0, 0, 100, 50), (2, 0, 959, 0), (1, 0, 120, 60)], f"touches written as >iiii and clamped {received[:3]}")
    unsub()
    await asyncio.sleep(0.8)
    check(api.calls[-1] == f"/ZidooControlCenter/setcastmode?mode=0&port={port}", "stops with mode=0 after grace period")
    json.dump(got[:40], open(OUT, "w"))

    # ---- flow control (no socket: frames fed straight into the session) ----
    fc = MirrorSession(FakeHass(), api)
    fc._config = b"\0\0\0\1cfg"
    def feed(key):
        if key: fc._gop, fc._gop_complete = [], True
        if len(fc._gop) < mirror_mod.MAX_GOP_FRAMES: fc._gop.append((key, b"x"))
        else: fc._gop_complete = False
        fc._deliver(key, b"x")
    old, new = [], []
    v_old, v_new = mirror_mod.Viewer(old.append), mirror_mod.Viewer(new.append)
    fc.start(v_old); fc.start(v_new)
    feed(True)
    check([m["type"] for m in new] == ["config", "frame"] and new[0]["viewer"] == v_new.id, "first key frame: config (with viewer id) + frame")
    fc.ack(v_new.id, 1)
    for _ in range(200): feed(False)
    check(len(old) == 202, "a card that never acknowledges (old version) is not limited")
    check(v_new.sent == 1 + mirror_mod.MAX_UNACKED_FRAMES + 1 and not v_new.synced, f"a card that stops acknowledging is paused after {v_new.sent} frames")
    n = len(new); feed(False); feed(False)
    check(len(new) == n, "paused: nothing more is queued for it")
    fc.ack(v_new.id, v_new.sent)
    burst = new[n:]
    check(burst[0]["type"] == "config" and burst[1]["key"] and len(burst) == 1 + len(fc._gop) and v_new.synced,
          f"caught up: continues from the last key frame (config + {len(burst) - 1} frames)")
    n = len(new); feed(False)
    check(len(new) == n + 1, "then live frames again")
    for _ in range(mirror_mod.MAX_UNACKED_FRAMES + 5): feed(False)
    check(not v_new.synced, "still not acknowledging after the burst: paused again, queue stays bounded")
    fc.ack(v_new.id, v_new.sent); n = len(new); feed(False)
    check(v_new.synced and len(new) == n + 1, "acknowledged: live again")
    # GOP too long to keep: a paused viewer waits for the next key frame
    mirror_mod.MAX_GOP_FRAMES = 5
    for _ in range(100): feed(False)
    fc.ack(v_new.id, v_new.sent); n = len(new)
    v_new.synced = False; fc.ack(v_new.id, v_new.sent)
    check(len(new) == n and not fc._gop_complete, "incomplete GOP is not replayed")
    feed(True)
    check([m["type"] for m in new[n:]] == ["config", "frame"] and new[n + 1]["key"], "next key frame brings it back")
    mirror_mod.MAX_GOP_FRAMES = 600
    # new stream parameters: everybody restarts at the next key frame (done by the read loop on a config packet)

    # ---- a card opening while the old stream is closing ---------------------
    class SlowApi(FakeApi):
        async def request(self, path, raw=False, timeout=5):
            if "mode=0" in path:
                await asyncio.sleep(0.2)   # the window in which a new viewer used to get its stream killed
            return await super().request(path, raw=raw, timeout=timeout)
    api3 = SlowApi(port)
    race = MirrorSession(FakeHass(), api3)
    v1, un1 = await race.async_subscribe(lambda m: None); race.start(v1)
    await asyncio.sleep(0.2)
    un1(); race._stop_handle.cancel(); race._stop_handle = None
    stopping = asyncio.create_task(race.async_stop())
    await asyncio.sleep(0.05)
    seen = []
    v2, un2 = await race.async_subscribe(seen.append); race.start(v2)
    await stopping; await asyncio.sleep(0.5)
    order = [("stop" if "mode=0" in c else "start") for c in api3.calls]
    check(order == ["start", "stop", "start"] and race.port == port and any(m["type"] == "frame" for m in seen)
          and not any(m["type"] == "ended" for m in seen), f"new viewer during stop: old stream closed first, new one lives {order}")
    un2(); race._stop_handle.cancel(); await race.async_shutdown()

    # ---- websocket commands -------------------------------------------
    import eversolo
    from homeassistant.components import websocket_api as ws
    from homeassistant.helpers import entity_registry
    hass = FakeHass(); hass.data = {}
    await eversolo.async_setup(hass, {})
    check(set(ws.COMMANDS) == {"eversolo/mirror/subscribe", "eversolo/mirror/touch", "eversolo/mirror/key", "eversolo/mirror/ack"}, "websocket commands registered")
    received.clear()
    api2 = FakeApi(port)
    class Coord: pass
    coord = Coord(); coord.api = api2; coord.mirror = MirrorSession(hass, api2)
    hass.data["eversolo"] = {"e1": coord}
    entity_registry.REG.map["media_player.eversolo"] = "e1"
    conn = ws.ActiveConnection()
    await ws.COMMANDS["eversolo/mirror/subscribe"](hass, conn, {"id": 5, "type": "eversolo/mirror/subscribe", "entity_id": "media_player.eversolo"})
    await asyncio.sleep(0.8)
    check(conn.sent[0] == {"id": 5, "type": "result", "success": True}, "subscribe answers result first")
    events = [m["event"] for m in conn.sent[1:]]
    check(events and events[0]["type"] == "config" and any(e["type"] == "frame" for e in events), f"then streams config and frames ({len(events)} events)")
    await ws.COMMANDS["eversolo/mirror/touch"](hass, conn, {"id": 6, "type": "eversolo/mirror/touch", "entity_id": "media_player.eversolo", "action": 0, "x": 10, "y": 20})
    await asyncio.sleep(0.2)
    check(received[:1] == [(0, 0, 10, 20)] and conn.sent[-1]["success"], "touch command reaches the socket")
    bad = ws.ActiveConnection()
    await ws.COMMANDS["eversolo/mirror/subscribe"](hass, bad, {"id": 7, "type": "eversolo/mirror/subscribe", "entity_id": "media_player.other"})
    check(bad.sent[0]["success"] is False and bad.sent[0]["error"] == "not_found", "unknown entity -> error")
    entity_registry.REG.map["media_player.eversolo_off"] = "e_not_loaded"
    off = ws.ActiveConnection()
    await ws.COMMANDS["eversolo/mirror/subscribe"](hass, off, {"id": 8, "type": "eversolo/mirror/subscribe", "entity_id": "media_player.eversolo_off"})
    check(off.sent[0]["success"] is False and off.sent[0]["error"] == "device_offline", "entry not loaded (player off) -> device_offline")
    conn.subscriptions[5]()
    await asyncio.sleep(0.8)
    check(api2.calls[-1].startswith("/ZidooControlCenter/setcastmode?mode=0"), "closing the subscription stops mirroring")
    server.close()
    print("FAILED:", check.failed)


asyncio.run(main())
