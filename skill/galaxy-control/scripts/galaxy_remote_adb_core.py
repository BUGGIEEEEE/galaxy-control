"""Fixed USB and optional TCP ADB profiles for an enrolled Galaxy."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum, unique

from galaxy_adb import (
    AdbError,
    AdbRuntime,
    adb_path,
    list_devices,
    normalize_model,
    run_adb,
    verify_endpoint,
)
from galaxy_process import JsonObject, RouteMetadata, error_envelope, success_envelope, with_route


@unique
class LegacyAction(StrEnum):
    DOCTOR = "doctor"
    STATUS = "status"
    ENABLE = "enable"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    RECOVER = "recover"
    RESTORE_USB = "restore-usb"


def _require_steady(runtime: AdbRuntime) -> None:
    if not runtime.profile.steady_adb_enabled:
        raise AdbError("steady_adb_disabled", "fixed TCP ADB is not enabled in this profile")


def _status(runtime: AdbRuntime) -> JsonObject:
    devices = list_devices(runtime)
    targets = tuple(
        device
        for device in devices
        if device.serial in {runtime.profile.physical_serial, runtime.profile.steady_endpoint}
    )
    return {
        "endpoint": runtime.profile.steady_endpoint,
        "steady_adb_enabled": runtime.profile.steady_adb_enabled,
        "usb_connected": any(
            device.serial == runtime.profile.physical_serial for device in targets
        ),
        "remote_connected": any(
            device.serial == runtime.profile.steady_endpoint for device in targets
        ),
        "duplicate_transports": len(targets) > 1,
        "devices": [
            {
                "serial": device.serial,
                "state": device.state,
                "transport": device.transport,
                "model": device.model,
            }
            for device in targets
        ],
        "security": {
            "adb_rsa_required": True,
            "tailscale_only_listener": False,
            "lan_exposure_possible": True,
        },
    }


def _enable(runtime: AdbRuntime) -> JsonObject:
    _require_steady(runtime)
    devices = list_devices(runtime)
    matches = tuple(
        device for device in devices if device.serial == runtime.profile.physical_serial
    )
    if len(matches) != 1:
        raise AdbError("adb_no_device", "the enrolled USB Galaxy is not uniquely connected")
    device = matches[0]
    if device.state == "unauthorized":
        raise AdbError("adb_unauthorized", "the enrolled Galaxy is unauthorized")
    if device.state == "offline":
        raise AdbError("adb_offline", "the enrolled Galaxy is offline")
    if (
        device.state != "device"
        or normalize_model(device.model or "") != runtime.profile.expected_model
    ):
        raise AdbError("device_mismatch", "USB Galaxy identity does not match the profile")
    response = run_adb(
        runtime,
        (adb_path(runtime), "-s", runtime.profile.physical_serial, "tcpip", "5555"),
    )
    if not response.succeeded:
        raise AdbError("adb_tcpip_failed", "failed to enable fixed TCP ADB")
    return {"enabled": True, "port": 5555, "verification_required": True}


def _connect(runtime: AdbRuntime) -> JsonObject:
    _require_steady(runtime)
    response = run_adb(runtime, (adb_path(runtime), "connect", runtime.profile.steady_endpoint))
    if not response.succeeded:
        raise AdbError("adb_connect_failed", "fixed endpoint connection failed")
    verified = verify_endpoint(runtime, runtime.profile.steady_endpoint, include_boot=True)
    return {
        "connected": True,
        "endpoint": verified.endpoint,
        "device_serial": verified.physical_serial,
        "model": verified.model,
        "boot_session_hash": verified.boot_session_hash,
    }


def _disconnect(runtime: AdbRuntime) -> JsonObject:
    _require_steady(runtime)
    response = run_adb(runtime, (adb_path(runtime), "disconnect", runtime.profile.steady_endpoint))
    if not response.succeeded:
        raise AdbError("adb_disconnect_failed", "fixed endpoint disconnect failed")
    return {"disconnected": True, "endpoint": runtime.profile.steady_endpoint}


def _restore_usb(runtime: AdbRuntime) -> JsonObject:
    _require_steady(runtime)
    response = run_adb(
        runtime,
        (adb_path(runtime), "-s", runtime.profile.steady_endpoint, "usb"),
    )
    if not response.succeeded:
        raise AdbError("restore_usb_failed", "failed to restore USB ADB mode")
    return {"restored": True, "remote_connection_will_close": True}


def execute_legacy(argv: Sequence[str], runtime: AdbRuntime) -> tuple[JsonObject, int]:
    """Execute one exact legacy profile."""
    action = argv[0] if argv else "unknown"
    try:
        match tuple(argv):  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
            case ("doctor",) | ("status",):
                result = _status(runtime)
            case ("enable", "--approved"):
                result = _enable(runtime)
            case ("enable",) | ("restore-usb",):
                raise AdbError("approval_required", "this command changes the ADB transport")
            case ("connect",) | ("recover",) | ("legacy-connect",):
                result = _connect(runtime)
            case ("disconnect",) | ("legacy-disconnect",):
                result = _disconnect(runtime)
            case ("restore-usb", "--approved"):
                result = _restore_usb(runtime)
            case _:
                raise AdbError("invalid_request", "unsupported ADB command or option")
    except AdbError as error:
        return error_envelope(action, error.code, error.message), 1
    mutating = action in {
        "enable",
        "disconnect",
        "legacy-disconnect",
        "restore-usb",
    }
    uses_remote = (
        action
        in {
            "connect",
            "recover",
            "legacy-connect",
            "disconnect",
            "legacy-disconnect",
            "restore-usb",
        }
        or result.get("remote_connected") is True
    )
    transport = "adb_tcpip" if uses_remote else "adb_usb"
    role = (
        "connect"
        if action
        in {
            "connect",
            "recover",
            "legacy-connect",
            "disconnect",
            "legacy-disconnect",
        }
        else "system"
    )
    verification_required = result.get("verification_required") is True or mutating
    routed = with_route(
        result,
        RouteMetadata(
            controller="adb",
            transport=transport,
            role=role,
            verification_required=verification_required,
            verify_with=("adb", "openminis") if verification_required else (),
        ),
    )
    return success_envelope(action, routed), 0
