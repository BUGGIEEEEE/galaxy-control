"""Official Wireless Debugging profiles for one enrolled Galaxy."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, NewType, assert_never

from galaxy_adb import (
    AdbDevice,
    AdbError,
    AdbRuntime,
    adb_path,
    list_devices,
    run_adb,
    verify_endpoint,
)
from galaxy_process import JsonObject, RouteMetadata, error_envelope, success_envelope, with_route
from galaxy_wireless_state import WirelessState, load_state, profile_hash, write_state

PAIR_CODE_PATTERN: Final = re.compile(r"^[0-9]{6}$")
MDNS_CONNECT_SERVICE: Final = "_adb-tls-connect._tcp"
ConnectionPort = NewType("ConnectionPort", int)


@unique
class WirelessAction(StrEnum):
    DOCTOR = "wireless-doctor"
    STATUS = "wireless-status"
    PREPARE = "wireless-prepare"
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


def parse_mdns_connection_ports(
    raw: str,
    physical_serial: str,
) -> tuple[ConnectionPort, ...]:
    """Return unique dynamic ports for the enrolled Galaxy's connect service."""
    service_prefix = f"adb-{physical_serial}-"
    ports: set[int] = set()
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        service_name, service_type, advertised_endpoint = fields
        if (
            not service_name.startswith(service_prefix)
            or service_type.removesuffix(".") != MDNS_CONNECT_SERVICE
        ):
            continue
        host, separator, raw_port = advertised_endpoint.rpartition(":")
        if not separator or not host:
            continue
        try:
            port = _port(raw_port, "connection_port_invalid")
        except AdbError:
            continue
        ports.add(int(port))
    return tuple(ConnectionPort(port) for port in sorted(ports))


def parse_request(argv: Sequence[str]) -> WirelessRequest:
    """Parse exact dynamic-port profiles without accepting host or serial input."""
    match tuple(argv):  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
        case ("wireless-doctor",):
            return WirelessRequest(WirelessAction.DOCTOR)
        case ("wireless-status",):
            return WirelessRequest(WirelessAction.STATUS)
        case ("wireless-prepare", "--approved"):
            return WirelessRequest(WirelessAction.PREPARE, approved=True)
        case ("wireless-prepare",):
            return WirelessRequest(WirelessAction.PREPARE)
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


def _enrolled_devices(
    runtime: AdbRuntime,
    devices: tuple[AdbDevice, ...],
) -> tuple[AdbDevice, ...]:
    return tuple(
        device
        for device in devices
        if device.serial == runtime.profile.physical_serial
        or device.serial.startswith(f"adb-{runtime.profile.physical_serial}-")
        or (
            device.serial.startswith(f"{runtime.profile.tailscale_ipv4}:")
            and device.serial != f"{runtime.profile.tailscale_ipv4}:5555"
        )
    )


def _status(runtime: AdbRuntime) -> JsonObject:
    devices = list_devices(runtime)
    expected = _enrolled_devices(runtime, devices)
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


def _prepare(request: WirelessRequest, runtime: AdbRuntime) -> JsonObject:
    if not request.approved:
        raise AdbError(
            "approval_required",
            "paired ADB reconnect requires current-request approval",
        )
    if not runtime.profile.auto_reconnect_adb_enabled:
        raise AdbError(
            "auto_reconnect_disabled",
            "paired ADB reconnect is not enabled in this profile",
        )
    if not runtime.profile.auto_reconnect_adb_enabled:
        raise AdbError(
            "auto_reconnect_disabled",
            "paired ADB reconnect is not enabled in this profile",
        )
    expected = _enrolled_devices(runtime, list_devices(runtime))
    if len(expected) > 1:
        raise AdbError(
            "duplicate_transports",
            "multiple enrolled Galaxy transports require review",
        )
    if expected:
        selected = next(iter(expected))
        verified = verify_endpoint(runtime, selected.serial, include_boot=True)
        if (
            runtime.profile.steady_adb_enabled
            and selected.transport == "tcpip"
            and not selected.serial.startswith(f"{runtime.profile.tailscale_ipv4}:")
        ):
            discovery = run_adb(runtime, (adb_path(runtime), "mdns", "services"))
            if not discovery.succeeded:
                raise AdbError(
                    "connection_port_required",
                    "current Wireless Debugging connection port is required",
                )
            ports = parse_mdns_connection_ports(
                discovery.stdout,
                runtime.profile.physical_serial,
            )
            if not ports:
                raise AdbError(
                    "connection_port_required",
                    "current Wireless Debugging connection port is required",
                )
            if len(ports) > 1:
                raise AdbError(
                    "mdns_ambiguous",
                    "multiple enrolled Wireless Debugging ports require review",
                )
            selected_port = next(iter(ports))
            connected = _connect(
                WirelessRequest(WirelessAction.CONNECT, selected_port, approved=True),
                runtime,
            )
            return {
                **connected,
                "ready": True,
                "reused": True,
                "source_endpoint": verified.endpoint,
                "discovery": "adb_mdns",
                "transport": "adb_tcpip",
            }
        connection_port: ConnectionPort | None = None
        if selected.serial.startswith(f"{runtime.profile.tailscale_ipv4}:"):
            connection_port = _port(
                selected.serial.rsplit(":", 1)[1],
                "connection_port_invalid",
            )
            if verified.boot_session_hash is None:
                raise AdbError(
                    "boot_session_unavailable",
                    "boot session could not be verified",
                )
            write_state(
                WirelessState(
                    endpoint=selected.serial,
                    port=int(connection_port),
                    boot_session_hash=verified.boot_session_hash,
                    profile_hash=profile_hash(runtime.profile),
                )
            )
        result: JsonObject = {
            "ready": True,
            "reused": True,
            "endpoint": verified.endpoint,
            "model": verified.model,
            "device_serial": verified.physical_serial,
            "boot_session_hash": verified.boot_session_hash,
            "transport": "adb_usb" if selected.transport == "usb" else "adb_tcpip",
        }
        if connection_port is not None:
            result["connection_port"] = int(connection_port)
        return result
    discovery = run_adb(runtime, (adb_path(runtime), "mdns", "services"))
    if not discovery.succeeded:
        raise AdbError(
            "connection_port_required",
            "current Wireless Debugging connection port is required",
        )
    ports = parse_mdns_connection_ports(
        discovery.stdout,
        runtime.profile.physical_serial,
    )
    if not ports:
        raise AdbError(
            "connection_port_required",
            "current Wireless Debugging connection port is required",
        )
    if len(ports) > 1:
        raise AdbError(
            "mdns_ambiguous",
            "multiple enrolled Wireless Debugging ports require review",
        )
    selected_port = next(iter(ports))
    connect_request = WirelessRequest(
        WirelessAction.CONNECT,
        selected_port,
        approved=True,
    )
    connected = _connect(connect_request, runtime)
    return {
        **connected,
        "ready": True,
        "reused": False,
        "discovery": "adb_mdns",
        "transport": "adb_tcpip",
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
    output = response.stdout.strip().lower()
    if (
        not response.succeeded
        or "failed" in output
        or "cannot" in output
        or not (
            output == "connected" or output.startswith(("connected to ", "already connected to "))
        )
    ):
        raise AdbError("adb_connect_failed", "wireless endpoint connection failed")
    try:
        verified = _verified_state(runtime, port)
    except AdbError as verification_error:
        cleanup = run_adb(runtime, (adb_path(runtime), "disconnect", selected))
        if not cleanup.succeeded:
            raise AdbError(
                "unverified_endpoint_cleanup_failed",
                "unverified ADB endpoint could not be disconnected",
            ) from verification_error
        raise
    if (
        cached is not None
        and request.action is WirelessAction.RECOVER
        and cached.boot_session_hash != verified.boot_session_hash
    ):
        cleanup = run_adb(runtime, (adb_path(runtime), "disconnect", selected))
        if not cleanup.succeeded:
            raise AdbError(
                "unverified_endpoint_cleanup_failed",
                "mismatched ADB endpoint could not be disconnected",
            )
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
            case WirelessAction.PREPARE:
                result = _prepare(request, runtime)
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
    mutating = request.action in {
        WirelessAction.PAIR,
        WirelessAction.PREPARE,
        WirelessAction.CONNECT,
        WirelessAction.RECOVER,
        WirelessAction.LEGACY_ENABLE,
        WirelessAction.DISCONNECT,
    }
    observed_transports: set[str] = set()
    devices_value = result.get("devices")
    if isinstance(devices_value, list):
        for item in devices_value:
            if isinstance(item, dict):
                transport_value = item.get("transport")
                if isinstance(transport_value, str):
                    observed_transports.add(transport_value)
    declared_transport = result.get("transport")
    if declared_transport == "adb_usb":
        transport = "adb_usb"
    elif declared_transport == "adb_tcpip":
        transport = "adb_tcpip"
    elif request.action in {
        WirelessAction.DOCTOR,
        WirelessAction.STATUS,
    } and observed_transports == {"usb"}:
        transport = "adb_usb"
    else:
        transport = "adb_tcpip"
    routed = with_route(
        result,
        RouteMetadata(
            controller="adb",
            transport=transport,
            role="connect"
            if request.action
            in {
                WirelessAction.PAIR,
                WirelessAction.PREPARE,
                WirelessAction.CONNECT,
                WirelessAction.RECOVER,
                WirelessAction.DISCONNECT,
            }
            else "system",
            verification_required=result.get("verification_required") is True or mutating,
            verify_with=("adb", "openminis")
            if result.get("verification_required") is True or mutating
            else (),
        ),
    )
    return success_envelope(action, routed), 0
