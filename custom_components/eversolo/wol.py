"""Wake on LAN: the same magic packet the Eversolo app sends (WakeThread)."""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time

from homeassistant.core import HomeAssistant

from .const import WOL_PORTS, WOL_REPEAT, WOL_REPEAT_DELAY_SECONDS

_LOGGER = logging.getLogger(__name__)


def normalize_mac(value: str | None) -> str | None:
    """'aa-bb-cc-dd-ee-ff', 'AABBCCDDEEFF', ... -> 'aa:bb:cc:dd:ee:ff'; None if it is not a MAC."""
    if not value:
        return None
    digits = re.sub(r"[^0-9a-fA-F]", "", str(value))
    if len(digits) != 12 or digits in ("000000000000", "ffffffffffff"):
        return None
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2)).lower()


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", ""))
    return b"\xff" * 6 + raw * 16


def broadcast_targets(host: str, broadcast: str | None) -> list[str]:
    """Where to send: the configured address, else the player's /24 and the limited broadcast.

    255.255.255.255 only reaches Home Assistant's own subnet; the player's subnet broadcast
    also works when HA sits in another VLAN and the router forwards directed broadcasts.
    """
    if broadcast:
        return [broadcast]
    targets = []
    try:
        addr = ipaddress.ip_address(host)
        if addr.version == 4:
            targets.append(str(ipaddress.ip_network(f"{host}/24", strict=False).broadcast_address))
    except ValueError:
        pass  # host name
    targets.append("255.255.255.255")
    return targets


def _send(packet: bytes, targets: list[str]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for attempt in range(WOL_REPEAT):
            if attempt:
                time.sleep(WOL_REPEAT_DELAY_SECONDS)
            for target in targets:
                for port in WOL_PORTS:
                    try:
                        sock.sendto(packet, (target, port))
                    except OSError as err:
                        _LOGGER.debug("WoL to %s:%s failed: %s", target, port, err)


async def async_wake(hass: HomeAssistant, mac: str, host: str, broadcast: str | None = None) -> None:
    targets = broadcast_targets(host, broadcast)
    _LOGGER.debug("Sending WoL for %s to %s", mac, targets)
    await hass.async_add_executor_job(_send, magic_packet(mac), targets)
