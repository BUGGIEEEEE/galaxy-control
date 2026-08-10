"""Official Wireless Debugging profiles for one enrolled Galaxy."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, NewType, assert_never

from galaxy_adb import AdbError, AdbRuntime, adb_path, list_devices, run_adb, verify_endpoint
from galaxy_process import JsonObject, error_envelope, success_envelope
from galaxy_wireless_state import WirelessState, load_state, profile_hash, write_state

PAIR_CODE_PATTERN: Final = re.compile(r"^[0-9]{6}$")
ConnectionPort = NewType("ConnectionPort", int)


@unique
class WirelessAction(StrEnum):
    DOCTOR = "wireless-doctor"
    STATUS = "wireless-status"
    PAIR = "wireless-pair"
    CONNECT = "wireless-connect"
    DISCONNECT = "wireless-disconnect"
    RECOVER = "wireless-recover"
    LEGACY_ENABLE = "legacy-enable-from-wireless"


@dataclass(frozen=True, slots=True)
class WirelessRequest:
    action: WirelessAction
    port: ConnectionPort | None = None
    approved: bool = False


def endpoint(runtime: AdbRuntime, port: ConnectionPort) -> str:
    return f"{runtime.profile.tailscale_ipv4}:{int(port)}"


def _port(raw: str, code: str) -> ConnectionPort:
    if not raw.isdecimal():
        raise AdbError(code, "port must contain decimal digits only")
    port = int(raw)
    if not 1 <= port <= 65535 or port == 5555:
        raise AdbError(code, "port is outside the allowed dynamic range")
    return ConnectionPort(port)


def parse_request(argv: Sequence[str]) -> WirelessRequest:
    """Parse exact dynamic-port profiles without accepting host or serial input."""
    match tuple(argv):  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
        case ("wireless-doctor",):
            return WirelessRequest(WirelessAction.DOCTOR)
        case ("wireless-status",):
            return WirelessRequest(WirelessAction.STATUS)
        case ("wireless-pair", "--port", raw, "--approved"):
            return WirelessRequest(
                WirelessAction.PAIR,
                _port(raw, "pair_port_invalid"),
                approved=True,
            )
        case ("wireless-pair", "--port", raw):
            return WirelessRequest(WirelessAction.PAIR, _port(raw, "pair_port_invalid"))
        case ("legacy-enable-from-wireless", "--port", raw, "--approved"):
            return WirelessRequest(
                WirelessAction.LEGACY_ENABLE,
                _port(raw, "connection_port_invalid"),
                approved=True,
            )
        case ("legacy-enable-from-wireless", "--port", raw):
            return WirelessRequest(
                WirelessAction.LEGACY_ENABLE,
                _port(raw, "connection_port_invalid"),
            )
        case (
            ("wireless-connect" | "wireless-disconnect" | "wireless-recover") as action,
            "--port",
            raw,
        ):
            return WirelessRequest(WirelessAction(action), _port(raw, "connection_port_invalid"))
        case _:
            raise AdbError("invalid_request", "unsupported wireless ADB command or option")


def _required_port(request: WirelessRequest) -> ConnectionPort:
    if request.port is None:
        raise AdbError("connection_port_invalid", "dynamic port is required")
    return request.port


def _status(runtime: AdbRuntime) -> JsonObject:
    devices = list_devices(runtime)
    expected = tuple(
        device
        for device in devices
        if device.serial == runtime.profile.physical_serial
        or device.serial.startswith(f"adb-{runtime.profile.physical_serial}-")
        or device.serial.startswith(f"{runtime.profile.tailscale_ipv4}:")
    )
    cached = load_state(runtime.profile)
    return {
        "steady_adb_enabled": runtime.profile.steady_adb_enabled,
        "duplicate_transports": len(expected) > 1,
        "cached_dynamic_endpoint": cached.endpoint if cached is not None else None,
        "devices": [
            {
                "serial": device.serial,
                "state": device.state,
                "transport": device.transport,
                "model": device.model,
            }
            for device in expected
        ],
    }


def _pair(request: WirelessRequest, runtime: AdbRuntime) -> JsonObject:
    if not request.approved:
        raise AdbError("approval_required", "wireless pairing changes ADB trust")
    code = runtime.pair_code_reader().strip()
    if PAIR_CODE_PATTERN.fullmatch(code) is None:
        raise AdbError("pair_code_invalid", "pairing code must contain six digits")
    selected = endpoint(runtime, _required_port(request))
    response = run_adb(runtime, (adb_path(runtime), "pair", selected), stdin=f"{code}\n")
    if not response.succeeded:
        raise AdbError("adb_pair_failed", "ADB pairing failed")
    return {"paired": True, "endpoint": selected, "pairing_code_logged": False}


def _verified_state(runtime: AdbRuntime, port: ConnectionPort) -> WirelessState:
    selected = endpoint(runtime, port)
    verified = verify_endpoint(runtime, selected, include_boot=True)
    if verified.boot_session_hash is None:
        raise AdbError("boot_session_unavailable", "boot session could not be verified")
    return WirelessState(
        endpoint=selected,
        port=int(port),
        boot_session_hash=verified.boot_session_hash,
        profile_hash=profile_hash(runtime.profile),
    )


def _connect(request: WirelessRequest, runtime: AdbRuntime) -> JsonObject:
    port = _required_port(request)
    selected = endpoint(runtime, port)
    cached = load_state(runtime.profile)
    if request.action is WirelessAction.RECOVER and (cached is None or cached.endpoint != selected):
        raise AdbError("boot_session_required", "recover requires matching cached state")
    response = run_adb(runtime, (adb_path(runtime), "connect", selected))
    if not response.succeeded:
        raise AdbError("adb_connect_failed", "wireless endpoint connection failed")
    verified = _verified_state(runtime, port)
    if (
        cached is not None
        and request.action is WirelessAction.RECOVER
        and cached.boot_session_hash != verified.boot_session_hash
    ):
        raise AdbError("boot_session_mismatch", "cached endpoint belongs to another boot")
    if request.action is WirelessAction.CONNECT:
        if cached is not None and cached.endpoint != selected:
            retired = run_adb(runtime, (adb_path(runtime), "disconnect", cached.endpoint))
            if not retired.succeeded:
                raise AdbError(
                    "previous_endpoint_disconnect_failed", "old endpoint was not retired"
                )
        write_state(verified)
    return {
        "connected": True,
        "endpoint": selected,
        "model": runtime.profile.expected_model,
        "device_serial": runtime.profile.physical_serial,
        "boot_session_hash": verified.boot_session_hash,
    }


def _legacy_enable(request: WirelessRequest, runtime: AdbRuntime) -> JsonObject:
    if not request.approved:
        raise AdbError("approval_required", "tcpip changes the ADB transport")
    if not runtime.profile.steady_adb_enabled:
        raise AdbError("steady_adb_disabled", "fixed TCP ADB is not enabled in this profile")
    port = _required_port(request)
    cached = load_state(runtime.profile)
    selected = endpoint(runtime, port)
    if cached is None or cached.endpoint != selected:
        raise AdbError("boot_session_required", "tcpip requires matching cached state")
    verified = _verified_state(runtime, port)
    if cached.boot_session_hash != verified.boot_session_hash:
        raise AdbError("boot_session_mismatch", "cached endpoint belongs to another boot")
    response = run_adb(runtime, (adb_path(runtime), "-s", selected, "tcpip", "5555"))
    if not response.succeeded:
        raise AdbError("adb_tcpip_failed", "failed to enable fixed TCP ADB")
    return {
        "enabled": True,
        "source_endpoint": selected,
        "final_endpoint": runtime.profile.steady_endpoint,
        "dynamic_transport_may_close": True,
        "verification_required": True,
    }


def _disconnect(request: WirelessRequest, runtime: AdbRuntime) -> JsonObject:
    selected = endpoint(runtime, _required_port(request))
    response = run_adb(runtime, (adb_path(runtime), "disconnect", selected))
    if not response.succeeded:
        raise AdbError("adb_disconnect_failed", "wireless endpoint disconnect failed")
    return {"disconnected": True, "endpoint": selected}


def execute_wireless(argv: Sequence[str], runtime: AdbRuntime) -> tuple[JsonObject, int]:
    """Execute one fixed official Wireless Debugging profile."""
    action = argv[0] if argv else "unknown"
    try:
        request = parse_request(argv)
        match request.action:
            case WirelessAction.DOCTOR | WirelessAction.STATUS:
                result = _status(runtime)
            case WirelessAction.PAIR:
                result = _pair(request, runtime)
            case WirelessAction.CONNECT | WirelessAction.RECOVER:
                result = _connect(request, runtime)
            case WirelessAction.LEGACY_ENABLE:
                result = _legacy_enable(request, runtime)
            case WirelessAction.DISCONNECT:
                result = _disconnect(request, runtime)
            case unreachable:
                assert_never(unreachable)
    except AdbError as error:
        return error_envelope(action, error.code, error.message), 1
    return success_envelope(action, result), 0
