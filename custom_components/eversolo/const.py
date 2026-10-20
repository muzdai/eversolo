"""Constants for the Eversolo integration."""

DOMAIN = "eversolo"
VERSION = "1.1.1"

CONF_NAME = "name"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CLIENT_UUID = "client_uuid"
CONF_FIRMWARE = "firmware"

DEFAULT_PORT = 9529
DEFAULT_NAME = "Eversolo"
CLIENT_NAME = "Home Assistant"
MDNS_SERVICE_TYPE = "_eversolo._tcp.local."

SCAN_INTERVAL_SECONDS = 2
SLOW_REFRESH_SECONDS = 60

CARD_URL = f"/{DOMAIN}/eversolo-player-card.js"

# Playback states reported by /ZidooMusicControl/v2/getState
STATE_IDLE = 0
STATE_PREPARING = 1
STATE_PREPARED = 2
STATE_PLAYING = 3
STATE_PAUSED = 4

# loopModel values
LOOP_LIST = 0
LOOP_SINGLE = 1
LOOP_SHUFFLE = 2

# VU / spectrum display (changVUDisplay openType)
VU_OPEN_TYPE = {"vu": 0, "spectrum": 1}
