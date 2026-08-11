"""Private per-install network identity for OpenMinis Control v2."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from .protocol import BridgeError

CONFIG_NAME: Final = "bridge.json"
MAX_CONFIG_BYTES: Final = 1_024
PRIVATE_FILE_MODE: Final = 0o600
TAILNET: Final = ipaddress.IPv4Network("100.64.0.0/10")
STATE_DIR: Final = (
    Path(os.environ.get("OPENMINIS_BRIDGE_HOME", str(Path.home() / ".openminis-bridge-control")))
    .expanduser()
    .resolve()
)


@dataclass(frozen=True, slots=True)
class BridgeNetwork:
    """Validated phone bind and trusted Mac Tailscale identities."""

    phone_ipv4: str
    trusted_mac_ipv4: str
    port: int
    config_sha256: str


def _tailnet_ipv4(raw: str) -> str:
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as error:
        raise BridgeError(1, "invalid_config", "bridge network config is invalid") from error
    if address not in TAILNET:
        raise BridgeError(1, "invalid_config", "bridge network config is invalid")
    return str(address)


def _read_private_config() -> bytes:
    path = STATE_DIR / CONFIG_NAME
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BridgeError(
            1, "config_unavailable", "bridge network config is unavailable"
        ) from error
    safe = (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and metadata.st_nlink == 1
        and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE
        and 0 < metadata.st_size <= MAX_CONFIG_BYTES
    )
    if not safe:
        raise BridgeError(1, "config_unavailable", "bridge network config is unsafe")
    try:
        return path.read_bytes()
    except OSError as error:
        raise BridgeError(
            1, "config_unavailable", "bridge network config is unavailable"
        ) from error


def load_network(expected_sha256: str | None = None) -> BridgeNetwork:
    """Read one canonical private network config and optionally pin its digest."""
    raw = _read_private_config()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and not hmac.compare_digest(digest, expected_sha256):
        raise BridgeError(1, "config_mismatch", "bridge network config identity changed")
    try:
        loaded = cast("object", json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BridgeError(1, "invalid_config", "bridge network config is invalid") from error
    if not isinstance(loaded, dict):
        raise BridgeError(1, "invalid_config", "bridge network config is invalid")
    payload = cast("dict[str, object]", loaded)
    if set(payload) != {
        "schema",
        "phone_ipv4",
        "trusted_mac_ipv4",
        "port",
    }:
        raise BridgeError(1, "invalid_config", "bridge network config is invalid")
    phone = payload.get("phone_ipv4")
    trusted_mac = payload.get("trusted_mac_ipv4")
    port = payload.get("port")
    if (
        payload.get("schema") != 1
        or not isinstance(phone, str)
        or not isinstance(trusted_mac, str)
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65_535
    ):
        raise BridgeError(1, "invalid_config", "bridge network config is invalid")
    parsed_phone = _tailnet_ipv4(phone)
    parsed_mac = _tailnet_ipv4(trusted_mac)
    if parsed_phone == parsed_mac:
        raise BridgeError(1, "invalid_config", "bridge peers must be distinct")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if raw != canonical:
        raise BridgeError(1, "invalid_config", "bridge network config is not canonical")
    return BridgeNetwork(parsed_phone, parsed_mac, port, digest)
