#!/usr/bin/env python3
"""
Minimal LAN client for Eversolo DMP / DAC devices, reverse-engineered from
Eversolo Controller 1.15.65 (com.eversolo.control). Standard library only.

Protocol summary (see eversolo_protocol.md for details):
  * Discovery : UDP multicast 239.39.3.9:18240, CRLF text messages (JOIN/REPLY/LEAVE)
  * Pairing   : GET http://<ip>:9529/ZidooControlCenter/connect?name=..&uuid=..&tag=0|1&type=1
  * Control   : plain HTTP GET on port 9529, JSON responses, no auth headers

Examples:
  python3 eversolo_client.py discover
  python3 eversolo_client.py --host 192.168.1.50 connect
  python3 eversolo_client.py --host 192.168.1.50 state
  python3 eversolo_client.py --host 192.168.1.50 play-pause
  python3 eversolo_client.py --host 192.168.1.50 volume 35
  python3 eversolo_client.py --host 192.168.1.50 key VolumeUp
  python3 eversolo_client.py --host 192.168.1.50 loop 2        # 0=list 1=single 2=shuffle
"""
import argparse
import json
import socket
import time
import urllib.parse
import urllib.request
import uuid as uuidlib

HTTP_PORT = 9529
DISCOVER_GROUP = "239.39.3.9"
DISCOVER_PORT = 18240
MUSIC = "/ZidooMusicControl/v2"
CTRL = "/ZidooControlCenter"

STATE_NAMES = {0: "idle", 1: "preparing", 2: "prepared", 3: "playing", 4: "paused"}
LOOP_NAMES = {0: "list", 1: "single", 2: "shuffle"}


class EversoloClient:
    def __init__(self, host, port=HTTP_PORT, timeout=3.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def get(self, path, raw=False):
        """GET a control path. Returns parsed JSON (or raw text if raw=True)."""
        url = self.base + path
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            body = r.read().decode("utf-8", "replace")
        if raw:
            return body
        try:
            return json.loads(body)
        except ValueError:
            return body

    # ---- pairing -------------------------------------------------------
    def connect(self, name="PythonController", client_uuid=None, ask_authority=True):
        """Register this controller with the device.
        status 200 = accepted; -2 = device is waiting for the user to allow it
        on its own screen (retry with ask_authority=True); -6/None = no answer."""
        client_uuid = client_uuid or str(uuidlib.uuid4())
        q = urllib.parse.urlencode({"name": name, "uuid": client_uuid,
                                    "tag": 1 if ask_authority else 0, "type": 1})
        resp = self.get(f"{CTRL}/connect?{q}")
        return client_uuid, resp

    # ---- playback state ------------------------------------------------
    def state(self):
        return self.get(f"{MUSIC}/getState")

    def play_pause(self):
        return self.get(f"{MUSIC}/playOrPause", raw=True)

    def next(self):
        return self.get(f"{MUSIC}/playNext", raw=True)

    def previous(self):
        return self.get(f"{MUSIC}/playLast", raw=True)

    def seek(self, value):
        """value uses the same unit as the 'duration' field of getState."""
        return self.get(f"{MUSIC}/seekTo?time={int(value)}", raw=True)

    def loop(self, mode):
        return self.get(f"{MUSIC}/setLoopMode?loop={int(mode)}", raw=True)

    def volume_get(self):
        return self.get(f"{MUSIC}/getSoundVolume")

    def volume_set(self, level):
        return self.get(f"{MUSIC}/setDevicesVolume?volume={int(level)}", raw=True)

    def play_queue(self, start=0, count=50):
        return self.get(f"{MUSIC}/getPlayQueue?start={start}&count={count}")

    def play_queue_remove(self, queue_id):
        return self.get(f"{MUSIC}/removePlayQueue?id={queue_id}", raw=True)

    def effects(self):
        return self.get(f"{MUSIC}/getEffects")

    def set_effect(self, index):
        return self.get(f"{MUSIC}/setEffect?effect={int(index)}", raw=True)

    def features(self):
        return self.get(f"{MUSIC}/getDeviceSupportedFeatures")

    def io_list(self):
        return self.get(f"{MUSIC}/getInputAndOutputList?isLight=true")

    def cover_url(self, music_id, music_type, kind=0, target=0):
        q = urllib.parse.urlencode({"id": music_id, "musicType": music_type,
                                    "type": kind, "target": target})
        return f"{self.base}{MUSIC}/getImage?{q}"

    # ---- remote-control keys (IR / remote emulation) -------------------
    def key(self, name):
        """name e.g. VolumeUp, VolumeDown, Mute, Back, Home, Menu, Ok, Up, Down,
        Left, Right, Info, MediaNext, MediaPrev, MediaForward, MediaBackward,
        MediaStop, PageUP, PageDown, Number_0..Number_9, Record, PopMenu."""
        return self.get(f"{CTRL}/RemoteControl/sendkey?key=Key.{name}", raw=True)

    def text(self, s):
        return self.get(f"{CTRL}/RemoteControl/inputtext?text={urllib.parse.quote(s)}", raw=True)

    def model(self):
        return self.get(f"{CTRL}/getModel")


def discover(wait=3.0, controller_uuid=None):
    """Multicast JOIN, then collect REPLY/ALIVE announcements for `wait` seconds."""
    controller_uuid = controller_uuid or str(uuidlib.uuid4())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", DISCOVER_PORT))
    mreq = socket.inet_aton(DISCOVER_GROUP) + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(0.5)
    join = (f"JOIN\r\nuuid: {controller_uuid}\r\ntype: 2\r\nhost: 0.0.0.0\r\n"
            f"port: {DISCOVER_PORT}\r\n\r\n").encode()
    sock.sendto(join, (DISCOVER_GROUP, DISCOVER_PORT))
    found = {}
    end = time.time() + wait
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        lines = data.decode("utf-8", "replace").split("\r\n")
        kind = lines[0].strip()
        if kind not in ("REPLY", "ALIVE", "SEARCH"):
            continue
        fields = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                fields[k.strip()] = v.strip()
        if fields.get("uuid") and fields.get("uuid") != controller_uuid:
            found[fields["uuid"]] = {"ip": fields.get("host", addr[0]), "kind": kind, **fields}
    sock.close()
    return list(found.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", help="device IP address")
    ap.add_argument("--port", type=int, default=HTTP_PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    sub.add_parser("connect")
    sub.add_parser("state")
    sub.add_parser("play-pause")
    sub.add_parser("next")
    sub.add_parser("prev")
    p = sub.add_parser("seek"); p.add_argument("value", type=int)
    p = sub.add_parser("volume"); p.add_argument("level", type=int, nargs="?")
    p = sub.add_parser("loop"); p.add_argument("mode", type=int, choices=[0, 1, 2])
    p = sub.add_parser("key"); p.add_argument("name")
    sub.add_parser("queue")
    sub.add_parser("features")
    args = ap.parse_args()

    if args.cmd == "discover":
        print(json.dumps(discover(), indent=2, ensure_ascii=False))
        return
    if not args.host:
        ap.error("--host is required for this command")
    c = EversoloClient(args.host, args.port)
    if args.cmd == "connect":
        cu, r = c.connect(ask_authority=False)
        if isinstance(r, dict) and r.get("status") == -2:
            print("Device wants confirmation on its screen; waiting...")
            time.sleep(1)
            cu, r = c.connect(client_uuid=cu, ask_authority=True)
        print(json.dumps({"client_uuid": cu, "response": r}, indent=2, ensure_ascii=False))
    elif args.cmd == "state":
        s = c.state()
        if isinstance(s, dict):
            summary = {
                "state": STATE_NAMES.get(s.get("state"), s.get("state")),
                "position": s.get("position"), "duration": s.get("duration"),
                "trackIndex": s.get("trackIndex"),
                "loop": LOOP_NAMES.get(s.get("loopModel"), s.get("loopModel")),
                "volume": (s.get("volumeData") or {}).get("currenttVolume"),
                "track": (s.get("playingMusic") or {}).get("name") or (s.get("playingMusic") or {}).get("title"),
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(s)
    elif args.cmd == "play-pause":
        print(c.play_pause())
    elif args.cmd == "next":
        print(c.next())
    elif args.cmd == "prev":
        print(c.previous())
    elif args.cmd == "seek":
        print(c.seek(args.value))
    elif args.cmd == "volume":
        print(json.dumps(c.volume_get(), indent=2) if args.level is None else c.volume_set(args.level))
    elif args.cmd == "loop":
        print(c.loop(args.mode))
    elif args.cmd == "key":
        print(c.key(args.name))
    elif args.cmd == "queue":
        print(json.dumps(c.play_queue(), indent=2, ensure_ascii=False))
    elif args.cmd == "features":
        print(json.dumps(c.features(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
