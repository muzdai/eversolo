# Eversolo Controller 1.15.65 — control protocol (reverse-engineered)

Source: `eversolo-controller-1-15-65.xapk` → `com.eversolo.control.apk` (versionCode 5065, flavor `Eversolo`, `IS_ZIDOO=false`).
Method: jadx decompilation of the Java code plus the decoded resources. **Nothing was captured on the wire.**
Every endpoint below comes from the code, so treat the "Confidence" notes as the real limit.

---

## 1. What the app is

The Eversolo controller is a fork of the Zidoo controller. Its code still uses Zidoo's package names, class
names and URL scheme (`ZidooControlCenter`, `ZidooMusicControl/v2`, `ZidooVideoPlay`, `ZidooPoster`,
`ZidooFileControl`). The Eversolo DMP/DAC firmware implements the same HTTP API, so most of the endpoints
here are the device's own API, not something the app invents.

Package layout worth knowing:

| Package | Role |
|---|---|
| `com.zidoo.control.phone.*` | the active (new) phone/tablet UI |
| `com.zidoo.control.old.phone.*` | legacy UI (same protocol, older endpoints) |
| `com.eversolo.mylibrary.musicmvp.MusicManager` | **the central client**: almost every playback call goes through here |
| `com.eversolo.mylibrary.musicmvp.MusicApiUrl` | URL constants |
| `com.eversolo.mylibrary.musicbean.MusicState` | JSON model of `getState` |
| `com.zidoo.control.phone.client.tool.ConnectionTool` | pairing (`connect`) |
| `com.zidoo.control.phone.client.discover.DiscoverManager` | UDP multicast discovery |

---

## 2. Transport

* **Protocol:** plain HTTP/1.1, no TLS, no auth header, no request signing. Every call is a **GET**
  (the app uses `OkGo`/`OkHttp`; a few setters are GET with query strings).
* **Port:** **TCP 9529** (`ConnectionTool`, `ScanTool`, `BuildConfig.SCANDEVICEPORTInt`=18240 is for discovery, not HTTP).
* **Base URL:** `http://<device-ip>:9529` (the `ZcpDevice.port` field defaults to 9529).
* **Response format:** JSON. Success is `"status": 200`. Errors use other codes; the app treats `-2` as
  "waiting for authorization" and `-6`/null as "no answer".
* **Cover art / images:** the same server serves images (see `getImage`), usually cached by Glide with a
  per-device signature.
* **Polling, not push:** `MusicManager` calls `getState` **once per second** (`TaskTimer.schedule(1000, 1000)`).
  I found no WebSocket or long-poll channel.

---

## 3. Discovery

### 3.1 UDP multicast (what the app actually uses for LAN discovery)

* Group: **`239.39.3.9`**, port **`18240`** (new app; the legacy app uses `18239`).
* Messages are CRLF text, **headers + blank line**, no body:

```
JOIN\r\n
uuid: <controller-uuid>\r\n
type: 2\r\n            # 2 = client (controller). Devices use 1 server, 3 DAC, 4 DMP.
host: <controller-ip>\r\n
port: 18240\r\n
\r\n
```

* Message keywords the app parses (`DiscoverRequest`): `JOIN`, `LEAVE`, `REPLY`, `ALIVE`, `SEARCH`, `ERROR`.
* Device replies carry the same headers. The app reads `uuid`, `host`, `port`, `name`, `scene`, `sceneCode`, `type`.
  It ignores type 1 (server) entries.
* Sent once on join (after 2 s it re-sends `JOIN`) and `LEAVE` on exit.

### 3.2 mDNS / JmDNS (fallback)

* Service type: **`_eversolo._tcp.local.`** (`BuildConfig.JmDNSName`). The app resolves the host with
  `getServiceInfo("_eversolo._tcp.local.", <uuid>, 3000)`.

### 3.3 Subnet port scan (last resort)

* `ScanTool` probes `http://<ip>:9529` across the /24 of the phone's Wi-Fi address (`ZidooControlCenter/...`).

---

## 4. Pairing (must be done once per controller)

```
GET /ZidooControlCenter/connect?name=<URL-encoded model>&uuid=<controller-uuid>&tag=<0|1>&type=1
```

* `tag=0` = just register. `tag=1` = "ask the user for authority": the device shows a confirmation on its own screen.
* Logic from `ConnectionTool`:
  1. `tag=0` → if `status == -2` the device wants confirmation → show prompt → `tag=1`.
  2. `status == 200` → the response contains the device object.
* Response (200), keys the app reads (top level, plus a `device` object):
  `device{…}`, `net_mac`, `firmware`, `dType`, `nationcode`, `appcode` (default 134), `hasDspSetting`,
  `hasEqSetting`, `configUrl`, `isNewphone`, `hasSouceInSetting`, `hasMultroom`, `deviceName`, `duuid`, `isOnlyOutput`.
* `uuid` is the controller's own identifier. Keep it stable so the device recognises you.

---

## 5. Playback state

```
GET /ZidooMusicControl/v2/getState
```

Returns the `MusicState` object as top-level JSON (no envelope). Main fields:

| Field | Meaning |
|---|---|
| `state` | 0 idle, 1 preparing, 2 prepared, 3 **playing**, 4 **paused** |
| `position` / `duration` | playback position and length (same unit; the seek bar treats them as proportional) |
| `trackIndex` | index inside the play queue (-1 = none) |
| `loopModel` | 0 list, 1 single cycle, 2 shuffle |
| `playType` | source type code (5 = local library, others = streaming/online/DLNA…) |
| `currentOutput` | active output/DAC index |
| `playingMusic`, `playingTrack` | current track object (`Music`: `name`, `artist`, `album`, `albumId`, `id`, `path`, `duration`, `bits`, `sampleRate`, `codec`, `favor`, `lrcFileName`, `albumArt`…) |
| `volumeData` | volume block (declared fields include `currenttVolume`, `maxVolume`, `minVolume`, `isMute`, `volumeTag`; check on device) |
| `hasFavor`, `hasLyric`, `hasPlayMode`, `hasPlayQueue`, `hasDspSetting`, `hasEQSetting`, `hasSubSetting`, `dspActive`, `eqActive`, `subActive` | feature flags |
| `everSoloPlayInfo` (nested bean in `MusicState.java`) | audio/output details (field names as declared; verify nesting on device): `outPutSampleRate`, `outPutBits`, `outPutChannels`, `outPutDecodec`, `outPutMqaType`, `audioSampleRate`, `audioBitsPerSample`, `isDsdOut`, `isMute`, `currenttVolume`, `intputTag`, `volumeTag` |

`MusicManager.getState` is also called by the phone home screen (`HomeActivityV2`, `HomeDevicesFragment2`).

---

## 6. Transport and volume controls

All of these are GETs on `/ZidooMusicControl/v2/`.

| Action | Request | Notes |
|---|---|---|
| Play / pause (toggle) | `playOrPause` | the main button; there is **no** separate play or pause call |
| Next | `playNext` | |
| Previous | `playLast` | |
| Seek | `seekTo?time=<n>` | `n` uses the same unit as `duration` in `getState`. The app sends `duration * fraction` |
| Loop mode | `setLoopMode?loop=<0\|1\|2>` | 0 list, 1 single, 2 shuffle |
| Absolute volume | `setDevicesVolume?volume=<n>` | `n` from `minVolume` to `maxVolume` |
| Read volume | `getSoundVolume` → `{"current":n,"max":m}` | |
| Sound/preset index | `setSoundVolume?index=<n>` | purpose not fully clear from code; treat as unverified |
| Mute | `setMuteVolume` (URL built in code; not verified) | the remote key path below is confirmed |
| Effect/filter | `getEffects`, `setEffect?effect=<n>` | |
| Feature list | `getDeviceSupportedFeatures` | use it to hide controls the device lacks |
| Output / input | `getInputAndOutputList?isLight=true`, `setInputList?tag=…`, `setOutInputList?tag=…`, `editInputSource?type=0&tag=…` | source & output switching |

### 6.1 Remote-key emulation (the "remote control" screen)

```
GET /ZidooControlCenter/RemoteControl/sendkey?key=Key.<Name>
GET /ZidooControlCenter/RemoteControl/inputtext?text=<URL-encoded>
GET /ZidooControlCenter/getScreenShot
GET /ZidooControlCenter/getModel            (optionally ?mode=1)
```

Key names seen in the app: `VolumeUp`, `VolumeDown`, `Mute`, `Back`, `Home`, `Menu`, `Ok`, `Up`, `Down`,
`Left`, `Right`, `Info`, `PopMenu`, `PageUP`, `PageDown`, `MediaPrev`, `MediaNext`, `MediaForward`,
`MediaBackward`, `MediaStop`, `Number_0`…`Number_9`, `Record`, `Resolution`, `PowerOn.Poweroff`,
`UserDefine_A`…`UserDefine_D`, plus the lowercase source names `music`, `movie`, `photo`, `file`.

Use the sendkey path for remote-style keys. Use the `ZidooMusicControl` calls above for playback.

---

## 7. Play queue and starting playback

| Action | Request |
|---|---|
| Read queue | `getPlayQueue?start=<n>&count=<m>` → `{"id":…,"start":…,"count":…,"total":…,"array":[…]}` |
| Read queue tabs | `getPlayQueueTab` |
| Remove one item | `removePlayQueue?id=<queueId>`; clear all: `removeAllPlayQueue` |
| Reorder | `playQueueDragSort` |
| Play a track now | `nextPlay?id=<musicId>` (plays it next) |
| Play an item from the queue | `playQueueMusic` |
| Start a playlist/album/folder | `playMusic?type=<t>&id=<id>&musicId=<mid>&musicType=<mt>&trackIndex=<i>&sort=<s>&playMode=<str>&genres=&categories=&artistId=&isSkipPlay=<bool>&albumType=&albumTypeId=` |
| Add and play | `addAndPlay?id=<id>&seekTime=0&dsfIndex=<i>` |
| Play a web/DLNA URL | `playWebMusic?url=<url>` |

Library browsing (for a custom UI): `getSongs`, `getAlbums`, `getAlbumMusics?id&start&count&sort`, `getArtists`,
`getArtistAlbums`, `getFolders`, `getFolderMusics`, `getSongLists`, `getSongListMusics`, `getFavorites`,
`searchMusic`, `searchAlbum`, `searchArtist`, `getRecentlyPlayMusics`. The list responses use an
envelope with `id`, `start`, `count`, `total`, `array`.

---

## 8. Images and lyrics

```
GET /ZidooMusicControl/v2/getImage?id=<id>&musicType=<t>&type=<k>&target=<x>
GET /ZidooMusicControl/v2/getDirectoryImage?path=<path>
GET /ZidooMusicControl/v2/getLyric?id=<id>&type=<t>&duration=<d>&number=<n>
GET /ZidooMusicControl/v2/searchSongLyrics?audioId=…&audioTitle=…&audioArtist=…
GET /ZidooMusicControl/v2/saveSongLyrics?selectIndex=…&audioId=…
```

---

## 9. Device settings (optional extras)

* DAC outputs: `GET /SystemSettings/dacSettings/getDacOutputList`, `…/setDacOutput?index=<n>`
* Name: `GET /SystemSettings/geneicSettings/setDeviceName?name=<name>`
* Playback settings: `/SystemSettings/playSettings/*`; display: `/SystemSettings/displaySettings/*`
* Power: `/ZidooMusicControl/v2/setPowerOption`, `getPowerOption`, `setTimePowerOff`, `getTimePowerOff`
* Multi-room: `/ZidooMusicControl/v2/mulltRoom/getAllDeviceList`,
  `…/mulltRoom/connectServer?server=<json>`, `…/mulltRoom/disconnectServer`
* DSP / EQ: `/ZidooMusicControl/v2/getDSPPresetList`, `getDSPConfig?id=`, `setDSPSource`, `setDSPPresetEQ`,
  `applyDrcFir`, `saveDSPConfig`, and so on (many endpoints; full list in `endpoints_all.txt`)

---

## 10. Cloud / config URLs the app fetches (not device control)

* `http://music.eversolo.com/dmp/config/eversolo_devices_v3.txt` — device catalogue
* `http://music.eversolo.com/dmp/config/ze_musicservice_dmp_new.txt` — music-service config
* `http://music.eversolo.com/dmp/config/eversolo_ad.txt` — welcome/ads
* `http://dl.eversolo.com/dac/app/eversolo_app_update_v2.txt` — app update
* `https://cloudxxxx22/a` — placeholder in `BuildConfig`; not a real host

---

## 11. Worked example (sequence)

```
1. UDP  JOIN → 239.39.3.9:18240        (device replies REPLY with its uuid/host)
2. GET  http://192.168.1.50:9529/ZidooControlCenter/connect?name=Pixel&uuid=U&tag=0&type=1
        → {"status":-2,...}            (device asks the user to allow)
3. GET  …/connect?…&tag=1&type=1       → {"status":200,"device":{…},"deviceName":"DMP-A6",…}
4. GET  …/ZidooMusicControl/v2/getState   → {"state":3,"position":…,"duration":…,"volumeData":{…},…}
5. GET  …/ZidooMusicControl/v2/playOrPause
6. GET  …/ZidooMusicControl/v2/setDevicesVolume?volume=35
7. GET  …/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeUp
```

A reference client that does exactly this is in `eversolo_client.py` (stdlib only):

```
python3 eversolo_client.py discover
python3 eversolo_client.py --host 192.168.1.50 connect
python3 eversolo_client.py --host 192.168.1.50 state
python3 eversolo_client.py --host 192.168.1.50 play-pause
python3 eversolo_client.py --host 192.168.1.50 volume 35
python3 eversolo_client.py --host 192.168.1.50 key VolumeUp
python3 eversolo_client.py --host 192.168.1.50 loop 2
```

---

## 12. Confidence and gaps

| Item | Status |
|---|---|
| Endpoint names and parameters | read directly from code (high) |
| `connect` flow and `status` codes | read from `ConnectionTool` (high) |
| Discovery multicast message format | read from `DiscoverManager` (high); not tested against a live device |
| `getState` JSON field names | taken from the `MusicState` class; the app maps them with Gson, so names match the declared fields. Nested bean membership unverified |
| Units of `seekTo?time` | proportional use confirmed; absolute unit (ms vs s) unverified |
| `setSoundVolume?index` meaning | unverified |
| `setMuteVolume` URL | not located in the code I read; use `sendkey?key=Key.Mute` |
| Response bodies of write calls | most return plain text; some return JSON. Check with `curl` |
| Firmware differences | the controller talks to many DMP/DAC models; capability flags from `getDeviceSupportedFeatures` decide what exists |

Recommended next step to confirm everything: run the client against your device and watch `getState` while
pressing buttons in the official app (or capture with a proxy on the same LAN). The discovery and
`connect` steps are the ones most worth checking on real hardware.
