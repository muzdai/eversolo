"""Constants for the Eversolo integration.

Values below are taken from the decompiled Eversolo Controller app (see docs/protocol.md).
"""

DOMAIN = "eversolo"

CONF_NAME = "name"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CLIENT_UUID = "client_uuid"
CONF_FIRMWARE = "firmware"
CONF_MODEL = "model"
CONF_MAC = "mac"
CONF_BROADCAST = "broadcast_address"

# Brightness settings of the player: API name -> entity key.
BRIGHTNESS_KINDS = {"Screen": "display_brightness", "Knob": "knob_brightness"}

DEFAULT_PORT = 9529
DEFAULT_NAME = "Eversolo"
DEFAULT_MODEL = "DMP / DAC"
CLIENT_NAME = "Home Assistant"
MDNS_SERVICE_TYPE = "_eversolo._tcp.local."

# The app polls getState and getInputAndOutputList every 2 s.
SCAN_INTERVAL_SECONDS = 2
# While the player is off there is nothing to read: ask less often.
OFFLINE_SCAN_INTERVAL_SECONDS = 10
# One lost answer is not "offline": keep the last state for this many failed polls in a row.
OFFLINE_AFTER_FAILURES = 3
# After a command, read the device back once it has had time to act on it.
CONFIRM_DELAY_SECONDS = 1.0
# Power menu and streaming-app list change rarely.
SLOW_REFRESH_SECONDS = 300

CARD_URL = f"/{DOMAIN}/eversolo-player-card.js"
ICONS_URL = f"/{DOMAIN}/eversolo-icons.js"

# MusicState.state (getState). The app treats 1, 2, 3 as "playing or preparing".
STATE_IDLE = 0
STATE_PREPARING = 1
STATE_PREPARED = 2
STATE_PLAYING = 3
STATE_PAUSED = 4

# everSoloPlayInfo.playStatus for non-library sources: the app treats 1 and 3 as playing.
PLAY_STATUS_PLAYING = (1, 3)

# MusicState.loopModel. The app cycles (loopModel + 1) % 4.
LOOP_REPEAT_ALL = 0  # "List cycle"
LOOP_REPEAT_ONE = 1  # "Single cycle"
LOOP_SHUFFLE = 2  # "Shuffle play"
LOOP_PLAY_ONCE = 3  # "List play" (stop at the end)
LOOP_MODES = {
    "repeat_all": LOOP_REPEAT_ALL,
    "repeat_one": LOOP_REPEAT_ONE,
    "shuffle": LOOP_SHUFFLE,
    "play_once": LOOP_PLAY_ONCE,
}
LOOP_NAMES = {v: k for k, v in LOOP_MODES.items()}

# changVUDisplay?openType=: 0 is the app's VU button, 1 its spectrum button.
# Each press moves the device to its next display mode; the current one is in
# getState vuDisplayMode / spDisplayMode. The app hides the VU button when
# vuDisplayMode < -1 and the spectrum button when spDisplayMode < 0.
VU_OPEN_TYPE = 0
SPECTRUM_OPEN_TYPE = 1

# getPowerOption entry handled by a separate dialog in the app, not a one-shot action.
POWER_TAG_TIMER = "timeshutdown"
# Power-menu tags for switching the player off, best first (getPowerOption / setPowerOption).
POWER_OFF_TAGS = ("poweroff", "shutdown", "standby", "sleep")

# Wake on LAN, as the app's WakeThread: magic packet (6 x 0xFF + MAC x 16) by UDP broadcast.
# The app sends to port 9517; 9 is the usual WoL port. The NIC accepts the packet on any port.
WOL_PORTS = (9, 9517)
# UDP may get lost: repeat the packet.
WOL_REPEAT = 3
WOL_REPEAT_DELAY_SECONDS = 0.1
# After "on" the player needs time to boot; after "off" it may still answer for a while.
SWITCH_ON_GRACE_SECONDS = 120
SWITCH_OFF_GRACE_SECONDS = 45

# getStreamMediaAppList appStatus: 0 installed, 1 not installed, 2 update available.
APP_STATUS_OPENABLE = (0, 2)
