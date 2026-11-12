"""Wake on LAN, power switch, MAC learning, dynamic power buttons, options flow."""
import asyncio
import sys

sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

import eversolo
from eversolo import switch as sw, wol, button as button_platform
from eversolo.api import EversoloApi, EversoloConnectionError
from eversolo.config_flow import EversoloOptionsFlow
from eversolo.coordinator import EversoloCoordinator

STATE = {"state": 3, "playingMusic": {"title": "x"}, "volumeData": {}}
POWER = {"status": 200, "data": [{"name": "Выключение", "tag": "poweroff"}, {"name": "Перезагрузка", "tag": "reboot"},
                                 {"name": "Экран", "tag": "screen"}, {"name": "Таймер", "tag": "timeshutdown"}]}


class Api(EversoloApi):
    def __init__(self):
        super().__init__(None, "192.168.1.46", 9529)
        self.online, self.calls, self.connect_reply = True, [], {"status": 200, "net_mac": "A0-B1-C2-D3-E4-F5"}

    async def request(self, path, *, raw=False, timeout=5):
        self.calls.append(path)
        if not self.online:
            raise EversoloConnectionError("refused")
        if "getState" in path: return dict(STATE)
        if "getInputAndOutputList" in path: return {"inputData": [], "outputData": []}
        if "getPowerOption" in path: return POWER
        if "getStreamMediaAppList" in path: return {"data": []}
        if "/connect" in path: return self.connect_reply
        return "ok"


class Entries:
    def __init__(self): self.updates = []
    def async_update_entry(self, entry, title=None, data=None):
        self.updates.append(data)
        if data is not None: entry.data = data
        if title is not None: entry.title = title


class Hass:
    def __init__(self):
        self.data, self.config_entries, self.tasks = {}, Entries(), []
    async def async_add_executor_job(self, fn, *args): return fn(*args)


class Entry(ConfigEntry):
    def __init__(self, data):
        super().__init__("e1", "Eversolo", data); self.unloads = []; self.tasks = []
    def async_on_unload(self, fn): self.unloads.append(fn)
    def async_create_background_task(self, hass, coro, name):
        t = asyncio.get_running_loop().create_task(coro); self.tasks.append(t); return t


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label); check.failed += not cond
check.failed = 0


async def main():
    # ---- wol helpers -----------------------------------------------------
    check(wol.normalize_mac("A0-B1-C2-D3-E4-F5") == "a0:b1:c2:d3:e4:f5" and wol.normalize_mac("a0b1c2d3e4f5") == "a0:b1:c2:d3:e4:f5", "MAC normalized")
    check(wol.normalize_mac("02:00:00:00:00") is None and wol.normalize_mac("00:00:00:00:00:00") is None and wol.normalize_mac(None) is None, "bad MACs rejected")
    pkt = wol.magic_packet("a0:b1:c2:d3:e4:f5")
    check(len(pkt) == 102 and pkt[:6] == b"\xff" * 6 and pkt[6:12] == bytes.fromhex("a0b1c2d3e4f5") and pkt[-6:] == pkt[6:12], "magic packet = 6xFF + MAC x16 (like the app)")
    check(wol.broadcast_targets("192.168.1.46", None) == ["192.168.1.255", "255.255.255.255"], "default targets: player /24 + limited broadcast")
    check(wol.broadcast_targets("eversolo.local", "10.0.0.255") == ["10.0.0.255"], "configured broadcast wins")
    sent = []
    wol._send.__globals__["socket"]  # module has socket
    import socket as _s
    class FakeSock:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def setsockopt(self, *a): sent.append(("opt", a))
        def sendto(self, data, addr): sent.append((len(data), addr))
    real = wol.socket.socket; wol.socket.socket = FakeSock
    await wol.async_wake(Hass(), "a0:b1:c2:d3:e4:f5", "192.168.1.46")
    wol.socket.socket = real
    check([s for s in sent if s[0] != "opt"][:4] == [(102, ("192.168.1.255", 9)), (102, ("192.168.1.255", 9517)), (102, ("255.255.255.255", 9)), (102, ("255.255.255.255", 9517))]
          and any(s[0] == "opt" and s[1][1] == _s.SO_BROADCAST for s in sent), "sent with SO_BROADCAST to ports 9 and 9517")

    # ---- power-off tag ---------------------------------------------------
    opts = [{"tag": "screen"}, {"tag": "reboot"}, {"tag": "poweroff"}]
    check(sw.power_off_tag(opts) == "poweroff", "poweroff picked (DMP-A6 menu)")
    check(sw.power_off_tag([{"tag": "screenoff"}, {"tag": "standby"}]) == "standby", "standby when there is no poweroff; screen-off never")
    check(sw.power_off_tag([{"tag": "screenoff"}, {"tag": "reboot"}]) is None, "no power-off entry -> None")

    # ---- switch ----------------------------------------------------------
    hass = Hass(); api = Api()
    coord = EversoloCoordinator(hass, api, "x"); await coord.async_refresh()
    entry = Entry({"host": "192.168.1.46", "port": 9529, "client_uuid": "u1"})
    s = sw.EversoloPowerSwitch(coord, entry); s.hass = hass
    check(s.is_on and s.available, "online -> on")
    api.online = False; [await coord.async_refresh() for _ in range(3)]
    check(not s.available, "offline without MAC -> unavailable")
    try:
        await s.async_turn_on(); check(False, "turn_on without MAC raises")
    except HomeAssistantError:
        check(True, "turn_on without MAC raises")
    entry.data = {**entry.data, "mac": "a0:b1:c2:d3:e4:f5"}
    check(s.available and not s.is_on, "offline with MAC -> available, off")
    woke = []
    async def fake_wake(h, mac, host, bc=None): woke.append((mac, host, bc))
    sw.async_wake = fake_wake
    await s.async_turn_on()
    check(woke == [("a0:b1:c2:d3:e4:f5", "192.168.1.46", None)] and s.is_on, "turn_on wakes and shows on while booting")
    from homeassistant.helpers import event as ev
    timer = [e for e in ev.SCHEDULED if not e["cancelled"] and e["action"] == s._async_grace_over]
    check(len(timer) == 1 and abs(timer[0]["delay"] - 120.5) < 1e-6, "a timer is set for the end of the grace period")
    s._pending_until = 0; w = s.writes; timer[0]["action"](None)
    check(not s.is_on and s.writes == w + 1, "player never woke up: the timer writes the state back to off")
    await s.async_turn_on(); api.online = True; await coord.async_refresh()
    check(s.is_on and s._pending is None, "player answers -> on, pending cleared")
    # player woken but power menu not read yet: turn_off reads it first
    coord.power_options = []
    api.calls.clear(); await s.async_turn_off()
    check(any("getPowerOption" in c for c in api.calls) and api.calls[-1].endswith("setPowerOption?tag=poweroff") and not s.is_on,
          "turn_off reads the menu, sends poweroff, shows off right away")
    s._pending_until = 0
    check(s.is_on, "still answering after the off grace period -> on again")
    api.online = False; [await coord.async_refresh() for _ in range(3)]; api.calls.clear(); coord.power_options = []
    await s.async_turn_off()
    check(api.calls == [], "turn_off while already off does nothing")
    try:
        import aiohttp
        class Dead:
            def get(self, *a, **k): raise aiohttp.ClientError("Cannot connect to host 192.168.1.46:9529")
        await EversoloApi(Dead(), "192.168.1.46").play_pause(); check(False, "offline command raises")
    except HomeAssistantError as err:
        check("192.168.1.46" in str(err) and "http" not in str(err), f"offline command -> readable HomeAssistantError ({err})")

    # ---- lost polls and offline polling -----------------------------------
    from datetime import timedelta
    hass = Hass(); api = Api()
    coord = EversoloCoordinator(hass, api, "x"); await coord.async_refresh()
    api.online = False
    await coord.async_refresh(); await coord.async_refresh()
    check(coord.last_update_success and coord.data and coord.update_interval == timedelta(seconds=2), "two lost answers: still available, last state kept")
    await coord.async_refresh()
    check(not coord.last_update_success and coord.update_interval == timedelta(seconds=10), "third lost answer: offline, polling every 10 s")
    coord.poll_fast(120); await coord.async_refresh()
    check(coord.update_interval == timedelta(seconds=2), "after a wake-up the 2 s polling stays on")
    api.online = True; await coord.async_refresh(); api.online = False; await coord.async_refresh()
    check(coord.last_update_success, "back online, one lost answer tolerated again")

    # ---- WoL repeats -----------------------------------------------------
    sent.clear(); wol.socket.socket = FakeSock; wol.time.sleep = lambda s: sent.append(("sleep", s))
    await wol.async_wake(Hass(), "a0:b1:c2:d3:e4:f5", "192.168.1.46", "192.168.1.255")
    wol.socket.socket = real
    check(sum(1 for x in sent if x[0] == 102) == 6 and sum(1 for x in sent if x[0] == "sleep") == 2, "magic packet sent 3 times (2 ports each)")

    # ---- MAC learning ----------------------------------------------------
    hass = Hass(); api = Api(); api.online = False
    coord = EversoloCoordinator(hass, api, "x"); await coord.async_refresh()
    entry = Entry({"host": "192.168.1.46", "port": 9529, "client_uuid": "u1"})
    eversolo._async_setup_mac_learning(hass, entry, coord)
    check(not entry.tasks, "offline -> no MAC request")
    api.online = True; await coord.async_refresh(); coord.async_update_listeners()
    await asyncio.gather(*entry.tasks)
    check(entry.data.get("mac") == "a0:b1:c2:d3:e4:f5" and any("/connect?" in c and "tag=0" in c for c in api.calls),
          "MAC learned from connect (tag=0) once online")
    n = len(entry.tasks); coord.async_update_listeners()
    check(len(entry.tasks) == n, "learned once per run")

    # ---- options reload only for name/host/port ---------------------------
    reloads = []
    class CE(Entries):
        async def async_reload(self, eid): reloads.append(eid)
    hass2 = Hass(); hass2.config_entries = CE()
    coord.settings = eversolo._reload_settings(entry); hass2.data["eversolo"] = {"e1": coord}
    await eversolo._async_options_updated(hass2, entry)
    check(reloads == [], "learned MAC does not reload the entry")
    entry.data = {**entry.data, "host": "192.168.1.47"}
    await eversolo._async_options_updated(hass2, entry)
    check(reloads == ["e1"], "new host reloads")

    # ---- dynamic power buttons ------------------------------------------
    hass = Hass(); api = Api(); api.online = False
    coord = EversoloCoordinator(hass, api, "x"); await coord.async_refresh()
    hass.data = {"eversolo": {"e1": coord}}
    entry = Entry({"host": "192.168.1.46", "port": 9529, "client_uuid": "u1"})
    added = []
    await button_platform.async_setup_entry(hass, entry, added.extend)
    check(len(added) == 2, "offline at start: only VU/spectrum buttons")
    api.online = True; await coord.async_refresh(); coord.async_update_listeners(); coord.async_update_listeners()
    tags = sorted(b._tag for b in added if hasattr(b, "_tag"))
    check(tags == ["poweroff", "reboot", "screen"], f"power buttons added once when the menu shows up {tags}")

    # ---- options flow ----------------------------------------------------
    entry = Entry({"host": "192.168.1.46", "port": 9529, "client_uuid": "u1"})
    flow = EversoloOptionsFlow(); flow.hass = Hass(); flow.config_entry = entry
    flow.async_show_form = lambda step_id, data_schema=None, errors=None, **k: {"type": "form", "errors": errors}
    flow.async_create_entry = lambda title, data: {"type": "create_entry"}
    r = await flow.async_step_init({"name": "Eversolo", "host": "192.168.1.46", "port": 9529, "mac": "zz"})
    check(r["type"] == "form" and r["errors"] == {"mac": "invalid_mac"}, "invalid MAC rejected")
    r = await flow.async_step_init({"name": "Eversolo", "host": "192.168.1.46", "port": 9529, "mac": "A0B1C2D3E4F5", "broadcast_address": "192.168.1.255"})
    check(r["type"] == "create_entry" and entry.data["mac"] == "a0:b1:c2:d3:e4:f5" and entry.data["broadcast_address"] == "192.168.1.255",
          "MAC + broadcast saved without contacting the (possibly off) player")
    r = await flow.async_step_init({"name": "Eversolo", "host": "192.168.1.46", "port": 9529, "broadcast_address": "x.y"})
    check(r["errors"] == {"broadcast_address": "invalid_broadcast"}, "invalid broadcast rejected")
    print("FAILED:", check.failed)

asyncio.run(main())
