"""Exercise the Eversolo integration against HA stubs and app-shaped device responses."""
import asyncio
import copy
import sys
from ipaddress import ip_address

sys.path.insert(0, sys.argv[1])  # stubs
sys.path.insert(0, sys.argv[2])  # repo custom_components dir

from homeassistant.components.media_player import MediaPlayerEntityFeature as F, MediaPlayerState, RepeatMode
from homeassistant.config_entries import AbortFlow, ConfigEntry, ConfigFlow
from homeassistant.core import ServiceCall
from homeassistant.helpers import entity_registry
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

import eversolo
from eversolo import api as api_mod
from eversolo.button import EversoloDisplayButton, EversoloPowerButton
from eversolo.config_flow import EversoloConfigFlow
from eversolo.const import CONF_MODEL, DOMAIN
from eversolo.coordinator import EversoloCoordinator
from eversolo.media_player import EversoloPlayer
from eversolo import select as select_platform
from eversolo.select import EversoloListSelect

STATE_LIB = {
    "state": 3, "position": 61234, "duration": 245000, "loopModel": 0,
    "vuDisplayMode": 0, "spDisplayMode": -1,
    "playingMusic": {"title": "Shine On", "artist": "Pink Floyd", "album": "WYWH", "albumArt": "",
                     "id": 42, "type": 0, "codec": "FLAC", "bits": "24", "sampleRate": "192 kHz", "number": 1},
    "volumeData": {"currenttVolume": 70, "maxVolume": 100, "minVolume": 0, "mMargin": 1,
                   "isMute": False, "isVolumeEnable": True, "display": "70"},
    "everSoloPlayInfo": {"everSoloPlayOutputInfo": {"outPutDecodec": "PCM", "outPutSampleRate": 192000, "outPutBits": 24}},
}
STATE_BT = {
    "state": 0, "playingMusic": None, "loopModel": 3, "vuDisplayMode": -2, "spDisplayMode": 1,
    "everSoloPlayInfo": {
        "playStatus": 1, "duration": 180000, "currentPosition": 5000,
        "isCanSeek": False, "isCanNextPlay": True, "isCanLastPlay": False, "isCanChangePlayStatus": True,
        "everSoloPlayAudioInfo": {"songName": "BT Song", "artistName": "Phone", "albumName": "",
                                  "albumUrl": "/img/bt.jpg", "audioSampleRate": 44100,
                                  "audioBitsPerSample": 16, "audioDecodec": "AAC"},
    },
    "volumeData": {"currenttVolume": 40, "maxVolume": 100, "mMargin": 2, "isMute": True},
}
IO = {"inputIndex": 0, "outputIndex": 1,
      "inputData": [{"tag": "internal", "name": "Internal player"}, {"tag": "BT", "name": "Bluetooth In"}],
      "outputData": [{"tag": "XLR", "name": "BAL-XLR"}, {"tag": "RCA", "name": "Analog-RCA"}]}
POWER = {"status": 200, "data": [{"name": "Standby", "tag": "standby"}, {"name": "Screen off", "tag": "screenoff"},
                                 {"name": "Timer", "tag": "timeshutdown"}]}
APPS = {"status": 200, "data": [{"title": "TIDAL", "packageName": "com.aspiro.tidal", "appStatus": 0},
                                {"title": "Qobuz", "packageName": "com.qobuz.music", "appStatus": 2},
                                {"title": "Spotify", "packageName": "com.spotify.music", "appStatus": 1}]}


class FakeApi(api_mod.EversoloApi):
    def __init__(self, state):
        super().__init__(None, "192.168.1.46", 9529)
        self.state = state
        self.calls = []
        self.connect_replies = []

    async def request(self, path, *, raw=False, timeout=5):
        self.calls.append(path)
        if path.startswith("/ZidooMusicControl/v2/getState"):
            return copy.deepcopy(self.state)
        if path.startswith("/ZidooMusicControl/v2/getInputAndOutputList"):
            return copy.deepcopy(IO)
        if path.startswith("/ZidooMusicControl/v2/getPowerOption"):
            return copy.deepcopy(POWER)
        if path.startswith("/ZidooMusicControl/v2/getStreamMediaAppList"):
            return copy.deepcopy(APPS)
        if path.startswith("/ZidooControlCenter/connect"):
            return self.connect_replies.pop(0)
        return "ok"


class FakeServices:
    def __init__(self):
        self.handlers = {}

    def has_service(self, domain, name):
        return (domain, name) in self.handlers

    def async_register(self, domain, name, handler, schema=None, supports_response=None):
        self.handlers[(domain, name)] = (handler, schema)


class FakeHass:
    def __init__(self):
        self.data = {}
        self.services = FakeServices()


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        check.failed += 1


check.failed = 0


async def make(state):
    api = FakeApi(state)
    coord = EversoloCoordinator(None, api, "dmp_a6")
    await coord.async_refresh()
    entry = ConfigEntry("e1", "dmp_a6", {"host": "192.168.1.46", "port": 9529, CONF_MODEL: "DMP-A6"})
    return api, coord, entry


async def main():
    # ---- parsers -------------------------------------------------------
    io = api_mod.parse_io(IO)
    check(io["inputs"][0]["selected"] and not io["inputs"][1]["selected"], "input selected by inputIndex")
    check(io["outputs"][1]["selected"] and io["outputs"][1]["index"] == 1, "output selected by outputIndex")
    power = api_mod.parse_power_options(POWER)
    check([p["tag"] for p in power] == ["standby", "screenoff"], "power menu drops timeshutdown")
    apps = api_mod.parse_apps(APPS)
    check([a["name"] for a in apps] == ["TIDAL", "Qobuz"], "apps keep appStatus 0 and 2 only")

    # ---- library playback ---------------------------------------------
    api, coord, entry = await make(STATE_LIB)
    check(coord.last_update_success and coord.last_update_success_time is not None, "coordinator refresh ok")
    check(len(coord.power_options) == 2 and len(coord.apps) == 2, "slow lists loaded on first refresh")
    p = EversoloPlayer(coord, entry)
    check(p.state == MediaPlayerState.PLAYING, "state 3 -> playing")
    check(p.media_title == "Shine On" and p.media_artist == "Pink Floyd", "title/artist from playingMusic")
    check(abs(p.media_position - 61.234) < 1e-6 and p.media_duration == 245.0, "positions are milliseconds")
    from datetime import timedelta
    t0 = p.media_position_updated_at
    # next polls: the player follows the clock -> same pair, attributes do not change
    for step in (2, 4, 6):
        api.state = {**STATE_LIB, "position": 61234 + step * 1000}
        await coord.async_refresh(); coord.last_update_success_time = t0 + timedelta(seconds=step)
        ok = abs(p.media_position - 61.234) < 1e-6 and p.media_position_updated_at == t0
    check(ok, "playing on schedule: position pair is not re-stamped every poll")
    api.state = {**STATE_LIB, "position": 120000}
    await coord.async_refresh(); t1 = coord.last_update_success_time = t0 + timedelta(seconds=8)
    check(p.media_position == 120.0 and p.media_position_updated_at == t1, "seek on the device: re-stamped")
    api.state = {**STATE_LIB, "state": 4, "position": 121000}
    await coord.async_refresh(); t2 = coord.last_update_success_time = t0 + timedelta(seconds=10)
    check(p.media_position == 121.0 and p.media_position_updated_at == t2, "pause: re-stamped")
    await coord.async_refresh(); coord.last_update_success_time = t0 + timedelta(seconds=12)
    check(p.media_position == 121.0 and p.media_position_updated_at == t2, "paused: nothing changes between polls")
    # live input: "playing" with a position that never moves
    api.state = {**STATE_LIB, "state": 3, "position": 0, "duration": 0}
    await coord.async_refresh(); t3 = coord.last_update_success_time = t0 + timedelta(seconds=14)
    p.media_position  # read once, as Home Assistant does on every update
    stamps = set()
    for step in (16, 18, 20):
        await coord.async_refresh(); coord.last_update_success_time = t0 + timedelta(seconds=step)
        stamps.add((p.media_position, p.media_position_updated_at))
    check(stamps == {(0.0, t3)}, "live input (position stuck at 0): not re-stamped")
    api.state = STATE_LIB; await coord.async_refresh()
    check(p.volume_level == 0.7 and p.is_volume_muted is False, "volume level")
    check(p.repeat == RepeatMode.ALL and p.shuffle is False, "loopModel 0 -> repeat all")
    check(p.source == "Internal player" and p.source_list == ["Internal player", "Bluetooth In"], "source from inputs")
    feats = p.supported_features
    check(all(feats & f for f in (F.PLAY, F.PAUSE, F.SEEK, F.NEXT_TRACK, F.PREVIOUS_TRACK, F.VOLUME_SET,
                                  F.VOLUME_STEP, F.VOLUME_MUTE, F.REPEAT_SET, F.SHUFFLE_SET, F.SELECT_SOURCE)),
          "library: all features")
    url = p._cover_url
    check(url == "http://192.168.1.46:9529/ZidooMusicControl/v2/getImage?id=42&musicType=0&type=4&target=16",
          "cover via getImage when albumArt empty")
    attrs = p.extra_state_attributes
    check(attrs["loop_mode"] == "repeat_all" and attrs["vu_mode"] == 0 and attrs["spectrum_mode"] == -1, "attrs modes")
    check(attrs["output_format"] == "PCM · 192 kHz · 24bit", "output format")
    check(attrs["app_list"] == ["TIDAL", "Qobuz"] and attrs["power_list"] == ["Standby", "Screen off"], "attrs lists")
    check(attrs["model"] == "DMP-A6", "model attribute")

    api.calls.clear()
    await p.async_media_seek(90.5)
    await p.async_set_volume_level(0.333)
    await p.async_set_repeat(RepeatMode.OFF)
    await p.async_set_repeat(RepeatMode.ONE)
    await p.async_set_shuffle(True)
    await p.async_volume_up()
    await p.async_mute_volume(True)
    await p.async_select_source("Bluetooth In")
    sent = [c for c in api.calls if not c.startswith(("/ZidooMusicControl/v2/getState", "/ZidooMusicControl/v2/getInputAndOutputList"))]
    expected = [
        "/ZidooMusicControl/v2/seekTo?time=90500",
        "/ZidooMusicControl/v2/setDevicesVolume?volume=33",
        "/ZidooMusicControl/v2/setLoopMode?loop=3",
        "/ZidooMusicControl/v2/setLoopMode?loop=1",
        "/ZidooMusicControl/v2/setLoopMode?loop=2",
        "/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeUp",
        "/ZidooControlCenter/RemoteControl/sendkey?key=Key.Mute",
        "/ZidooMusicControl/v2/setInputList?tag=BT&index=1&isLight=true",
    ]
    check(sent == expected, "player actions send app-identical URLs")
    if sent != expected:
        print("   got:", sent)

    # ---- instant feedback -----------------------------------------------
    from homeassistant.helpers import event as ev
    ev.SCHEDULED.clear()
    check(coord.debouncer.cooldown == 0.3, "refresh debouncer cooldown 0.3 s")
    await p.async_media_seek(30)
    check(coord.data["position"] == 30000 and ev.SCHEDULED and ev.SCHEDULED[-1]["delay"] == 1.0, "seek shows new position at once and confirms in 1 s")
    await p.async_set_volume_level(0.5)
    check(coord.data["volumeData"]["currenttVolume"] == 50, "volume shown at once")
    await p.async_media_play_pause()
    check(p.state == MediaPlayerState.PAUSED, "play/pause flips at once")
    await p.async_select_source("Bluetooth In")
    check(p.source == "Bluetooth In", "input shown at once")
    check(sum(1 for e in ev.SCHEDULED if not e["cancelled"]) == 1, "only one pending confirm")
    await ev.SCHEDULED[-1]["action"](None)
    check(p.state == MediaPlayerState.PLAYING and p.source == "Internal player", "confirm re-reads the device")

    # ---- selects and buttons ------------------------------------------
    sel_in = EversoloListSelect(coord, entry, "input", "inputs")
    sel_out = EversoloListSelect(coord, entry, "output", "outputs")
    check(sel_in.current_option == "Internal player" and sel_out.current_option == "Analog-RCA", "select current options")
    check(not hasattr(sel_in, "_attr_name"), "selects rely on translation_key (no hardcoded name)")
    api.calls.clear()
    await sel_out.async_select_option("BAL-XLR")
    check("/ZidooMusicControl/v2/setOutInputList?tag=XLR&index=0&isLight=true" in api.calls, "output select URL")
    from homeassistant.helpers import entity_registry as _er
    _er.REG.uids[("select", "eversolo", f"{entry.entry_id}_app")] = "select.eversolo_app"
    added = []
    _hass = type("H", (), {"data": {"eversolo": {entry.entry_id: coord}}})()
    await select_platform.async_setup_entry(_hass, entry, added.extend)
    check(_er.REG.removed == ["select.eversolo_app"] and len(added) == 2, "app select removed, only input/output selects added")
    vu = EversoloDisplayButton(coord, entry, "vu")
    sp = EversoloDisplayButton(coord, entry, "spectrum")
    check(vu.available and not sp.available, "vu available (0), spectrum hidden (-1)")
    api.calls.clear()
    await vu.async_press()
    check(api.calls[0] == "/ZidooMusicControl/v2/changVUDisplay?openType=0", "vu button -> openType 0")
    pw = [EversoloPowerButton(coord, entry, o) for o in coord.power_options]
    check([b._attr_name for b in pw] == ["Standby", "Screen off"] and pw[1]._attr_unique_id == "e1_power_screenoff",
          "power buttons named by device")
    api.calls.clear()
    await pw[1].async_press()
    check(api.calls == ["/ZidooMusicControl/v2/setPowerOption?tag=screenoff"], "power button URL")

    # ---- external source (Bluetooth) ----------------------------------
    api2, coord2, entry2 = await make(STATE_BT)
    b = EversoloPlayer(coord2, entry2)
    check(b.state == MediaPlayerState.PLAYING, "external playStatus 1 -> playing")
    check(b.media_title == "BT Song" and b.media_duration == 180.0 and b.media_position == 5.0, "external track info")
    f2 = b.supported_features
    check(not (f2 & F.SEEK) and not (f2 & F.PREVIOUS_TRACK) and f2 & F.NEXT_TRACK and f2 & F.PLAY, "external features follow flags")
    check(b.repeat == RepeatMode.OFF, "loopModel 3 -> repeat off")
    check(b._cover_url == "http://192.168.1.46:9529/img/bt.jpg", "external cover from albumUrl")
    a2 = b.extra_state_attributes
    check(a2["sample_rate"] == "44.1 kHz" and a2["bits"] == 16 and a2["codec"] == "AAC", "external format attrs")
    check(EversoloDisplayButton(coord2, entry2, "spectrum").available and not EversoloDisplayButton(coord2, entry2, "vu").available,
          "vu hidden (-2), spectrum shown (1)")
    api2.calls.clear()
    await b.async_set_volume_level(0.55)
    check("/ZidooMusicControl/v2/setDevicesVolume?volume=56" in api2.calls, "volume snaps to mMargin steps")

    # ---- services ------------------------------------------------------
    hass = FakeHass()
    hass.data[DOMAIN] = {"e1": coord}
    entity_registry.REG.map["media_player.dmp_a6"] = "e1"
    eversolo._async_register_services(hass)
    names = sorted(n for _, n in hass.services.handlers)
    check(names == ["open_app", "power", "request", "set_input", "set_loop_mode", "set_output", "spectrum_next", "vu_next"],
          "services registered")
    h = lambda n: hass.services.handlers[(DOMAIN, n)][0]
    api.calls.clear()
    await h("set_loop_mode")(ServiceCall({"entity_id": "media_player.dmp_a6", "mode": "play_once"}))
    await h("open_app")(ServiceCall({"entity_id": "media_player.dmp_a6", "name": "com.aspiro.tidal"}))
    await h("power")(ServiceCall({"entity_id": "media_player.dmp_a6", "name": "Standby"}))
    await h("set_input")(ServiceCall({"entity_id": "media_player.dmp_a6", "name": "BT"}))
    await h("spectrum_next")(ServiceCall({"entity_id": "media_player.dmp_a6"}))
    svc = [c for c in api.calls if not c.startswith(("/ZidooMusicControl/v2/getState", "/ZidooMusicControl/v2/getInputAndOutputList"))]
    check(svc == ["/ZidooMusicControl/v2/setLoopMode?loop=3",
                  "/ZidooControlCenter/Apps/openApp?packageName=com.aspiro.tidal",
                  "/ZidooMusicControl/v2/setPowerOption?tag=standby",
                  "/ZidooMusicControl/v2/setInputList?tag=BT&index=1&isLight=true",
                  "/ZidooMusicControl/v2/changVUDisplay?openType=1"], "service URLs")
    schema = hass.services.handlers[(DOMAIN, "set_loop_mode")][1]
    try:
        schema({"entity_id": "x", "mode": "list"})
        check(False, "old loop mode name rejected")
    except ValueError:
        check(True, "old loop mode name rejected")

    # ---- config flow ---------------------------------------------------
    flow_api = FakeApi(STATE_LIB)
    flow = EversoloConfigFlow()
    flow.hass, flow.context = None, {}
    flow._api = lambda: flow_api
    info = ZeroconfServiceInfo(ip_address=ip_address("192.168.1.46"), port=9529, name="66065e95._eversolo._tcp.local.",
                               properties={"name": "DMP-A6", "deviceName": "Spalnia", "uuid": "66065e95", "port": "9529"})
    form = await flow.async_step_zeroconf(info)
    check(form["step_id"] == "user" and flow.context["title_placeholders"] == {"name": "Spalnia"}, "zeroconf shows device name")
    check(flow._name == "Spalnia" and flow._model == "DMP-A6", "zeroconf prefill name and model")
    flow_api.connect_replies = [{"status": -2}, {"status": -6}]
    res = await flow.async_step_user({"name": "Spalnia", "host": "192.168.1.46", "port": 9529})
    check(res["step_id"] == "authorize" and res["errors"] == {"base": "not_authorized"}, "timeout -> authorize retry form")
    calls = [c for c in flow_api.calls if "connect" in c]
    check("tag=0" in calls[0] and "tag=1" in calls[1], "tag=1 sent right after -2")
    flow_api.connect_replies = [{"status": 200, "duuid": "D-1", "firmware": "1.2.3", "device": {"name": "DMP-A6"}}]
    res = await flow.async_step_authorize({})
    check(res["type"] == "create_entry" and res["data"][CONF_MODEL] == "DMP-A6" and res["unique_id"] == "D-1",
          "entry created with model and device uuid")

    flow2 = EversoloConfigFlow()
    flow2.hass, flow2.context = None, {}
    ConfigFlow._existing = [("D-1", {"host": "192.168.1.46"})]
    try:
        await flow2.async_step_zeroconf(info)
        check(False, "rediscovery of configured host aborts")
    except AbortFlow as err:
        check(err.reason == "already_configured", "rediscovery of configured host aborts")
    ConfigFlow._existing = []

    # the same player at a new address: matched by MAC, entry updated, flow aborted
    known = ConfigEntry("e9", "DMP-A8", {"host": "192.168.1.46", "port": 9529, "mac": "80:0a:80:5d:51:df"})
    updated = []
    class Entries:
        def async_update_entry(self, entry, data=None, title=None): entry.data = data; updated.append(data)
    flow3 = EversoloConfigFlow()
    flow3.hass, flow3.context = type("H", (), {"config_entries": Entries()})(), {}
    ConfigFlow._entries = [known]
    moved = ZeroconfServiceInfo(ip_address=ip_address("192.168.1.99"), port=9529, name="x._eversolo._tcp.local.",
                                properties={"name": "DMP-A8", "uuid": "other-id", "net_mac": "80:0A:80:5D:51:DF", "port": "9529"})
    res = await flow3.async_step_zeroconf(moved)
    check(res == {"type": "abort", "reason": "already_configured"} and known.data["host"] == "192.168.1.99",
          "known MAC at a new address: entry gets the new host")
    known2 = ConfigEntry("e8", "DMP-A8", {"host": "192.168.1.46", "port": 9529}); known2.unique_id = "80:0a:80:5d:51:df"
    ConfigFlow._entries = [known2]
    res = await flow3.async_step_zeroconf(moved)
    check(res["type"] == "abort" and known2.data["host"] == "192.168.1.99" and known2.data["mac"] == "80:0a:80:5d:51:df",
          "entry without stored MAC is matched by its unique id")
    ConfigFlow._entries = []

    # ---- request service: administrators only ----------------------------
    from homeassistant.exceptions import Unauthorized
    class Auth:
        async def async_get_user(self, uid): return type("U", (), {"is_admin": uid == "admin"})()
    hass.auth = Auth()
    req = hass.services.handlers[(DOMAIN, "request")][0]
    r = await req(ServiceCall({"entity_id": "media_player.dmp_a6", "path": "/x"}, user_id="admin"))
    try:
        await req(ServiceCall({"entity_id": "media_player.dmp_a6", "path": "/x"}, user_id="guest")); denied = False
    except Unauthorized:
        denied = True
    r2 = await req(ServiceCall({"entity_id": "media_player.dmp_a6", "path": "/x"}))  # automation / script: no user
    check(r == {"response": "ok"} and denied and r2 == {"response": "ok"}, "request: admin and automations allowed, other users refused")

    # ---- explicit play / pause read the player first ----------------------
    api, coord, entry = await make(STATE_LIB)
    p = EversoloPlayer(coord, entry)
    api.state = {**STATE_LIB, "state": 4}          # paused on the device since the last poll
    api.calls.clear(); await p.async_media_pause()
    check(not any("playOrPause" in c for c in api.calls), "pause on an already paused player does not toggle it back on")
    api.calls.clear(); await p.async_media_play()
    check(sum("playOrPause" in c for c in api.calls) == 1 and p.state == MediaPlayerState.PLAYING, "play toggles once")
    api.calls.clear(); await p.async_media_pause()
    check(sum("getState" in c for c in api.calls) == 0 and sum("playOrPause" in c for c in api.calls) == 1,
          "right after a command the optimistic state is used (no stale re-read)")

    # ---- removing the last player removes the card resource ---------------
    class Res:
        def __init__(self): self.items = [{"id": "1", "url": "/eversolo/eversolo-player-card.js?v=1"}, {"id": "2", "url": "/local/other.js"}]
        def async_items(self): return self.items
        async def async_create_item(self, d): pass
        async def async_delete_item(self, i): self.items = [x for x in self.items if x["id"] != i]
    res_store = Res()
    class CE:
        def __init__(self, entries): self.entries = entries
        def async_entries(self, domain): return self.entries
    gone = ConfigEntry("e1", "x", {})
    h2 = type("H", (), {})(); h2.data = {"lovelace": type("L", (), {"resources": res_store})()}
    h2.config_entries = CE([gone, ConfigEntry("e2", "y", {})])
    await eversolo.async_remove_entry(h2, gone)
    kept = len(res_store.items)
    h2.config_entries = CE([gone])
    await eversolo.async_remove_entry(h2, gone)
    check(kept == 2 and [x["id"] for x in res_store.items] == ["2"], "card resource removed only with the last player")

    print("\nFAILED:", check.failed)
    return check.failed


sys.exit(asyncio.run(main()))
