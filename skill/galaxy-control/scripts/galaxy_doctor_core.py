"""Read-only, partial Galaxy Control diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from galaxy_adb import normalize_model, parse_devices
from galaxy_process import JsonObject, JsonValue, Runner
from galaxy_profile import DeviceProfile
from openminis_client import ClientError, SuccessResponse
from openminis_protocol import Action, BridgeRequest


@dataclass(frozen=True, slots=True)
class DoctorRuntime:
    """Injectable read-only diagnostic boundaries."""

    profile: DeviceProfile
    runner: Runner
    which: Callable[[str], str | None]
    bridge: Callable[[BridgeRequest], SuccessResponse]


@unique
class PreflightTarget(StrEnum):
    """Fixed path sets accepted by the read-only doctor."""

    ALL = "all"
    OPENMINIS = "openminis"
    ADB = "adb"
    SCRCPY = "scrcpy"


class _TailscaleSelf(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    online: bool = Field(default=False, alias="Online")


class _TailscaleStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    backend_state: str = Field(default="unknown", alias="BackendState")
    self_status: _TailscaleSelf = Field(default_factory=_TailscaleSelf, alias="Self")


def _bridge_status(runtime: DoctorRuntime, action: Action) -> JsonObject:
    try:
        response = runtime.bridge(BridgeRequest(action))
    except ClientError as error:
        return {"available": False, "error": error.code}
    return {"available": True, "result": cast("JsonValue", response.result)}


def _version(runtime: DoctorRuntime, name: str, argv: tuple[str, ...]) -> JsonObject:
    path = runtime.which(name)
    if path is None:
        return {"installed": False}
    response = runtime.runner((path, *argv))
    value = response.stdout.strip().splitlines()
    return {
        "installed": response.succeeded,
        "path": path,
        "version": value[0] if response.succeeded and value else None,
    }


def _adb_status(runtime: DoctorRuntime) -> JsonObject:
    adb = runtime.which("adb")
    if adb is None:
        return {"installed": False, "devices": [], "error": "adb_not_installed"}
    version = runtime.runner((adb, "version"))
    listing = runtime.runner((adb, "devices", "-l"))
    if not listing.succeeded:
        return {"installed": True, "devices": [], "error": "adb_devices_failed"}
    devices = parse_devices(listing.stdout)
    remote_candidates = [
        device
        for device in devices
        if device.state == "device"
        and device.serial.startswith(f"{runtime.profile.tailscale_ipv4}:")
        and device.model is not None
        and normalize_model(device.model) == runtime.profile.expected_model
    ]
    remote_serials: set[str] = set()
    for device in remote_candidates:
        physical = runtime.runner(
            (
                adb,
                "-s",
                device.serial,
                "shell",
                "getprop",
                "ro.serialno",
            )
        )
        if physical.succeeded and physical.stdout.strip() == runtime.profile.physical_serial:
            remote_serials.add(device.serial)
    encoded: list[JsonValue] = [
        {
            "serial": device.serial,
            "state": device.state,
            "transport": device.transport,
            "model": device.model,
        }
        for device in devices
    ]
    matches = [
        device
        for device in devices
        if device.state == "device"
        and (device.serial == runtime.profile.physical_serial or device.serial in remote_serials)
        and device.model is not None
        and normalize_model(device.model) == runtime.profile.expected_model
    ]
    result: JsonObject = {
        "installed": True,
        "version": version.stdout.strip().splitlines()[0] if version.succeeded else None,
        "devices": encoded,
        "identity_match": len(matches) == 1,
    }
    if devices and not matches:
        result["error"] = "device_mismatch"
    elif not devices:
        result["error"] = "adb_no_device"
    return result


def _tailscale_status(runtime: DoctorRuntime) -> JsonObject:
    path = runtime.which("tailscale")
    if path is None:
        return {"installed": False, "online": False}
    response = runtime.runner((path, "status", "--json"))
    online = False
    backend = "unknown"
    if response.succeeded:
        try:
            payload = _TailscaleStatus.model_validate_json(response.stdout)
        except ValidationError:
            payload = None
        else:
            backend = payload.backend_state
            online = payload.self_status.online and backend == "Running"
    return {"installed": True, "online": online, "backend_state": backend}


def _bridge_available(value: JsonValue) -> bool:
    return isinstance(value, dict) and value.get("available") is True


def _shizuku_ready(value: JsonValue) -> bool:
    if not isinstance(value, dict) or value.get("available") is not True:
        return False
    detail = value.get("result")
    return (
        isinstance(detail, dict)
        and detail.get("running") is True
        and detail.get("authorized") is True
    )


def inspect_device(
    runtime: DoctorRuntime,
    target: PreflightTarget = PreflightTarget.ALL,
) -> JsonObject:
    """Inspect only the fixed path set required by the requested task."""
    check_openminis = target in {PreflightTarget.ALL, PreflightTarget.OPENMINIS}
    check_adb = target in {PreflightTarget.ALL, PreflightTarget.ADB, PreflightTarget.SCRCPY}
    check_scrcpy = target in {PreflightTarget.ALL, PreflightTarget.SCRCPY}
    check_all = target is PreflightTarget.ALL

    openminis: JsonObject = (
        {
            "health": _bridge_status(runtime, Action.HEALTH),
            "accessibility": _bridge_status(runtime, Action.A11Y_STATUS),
            **({"shizuku": _bridge_status(runtime, Action.SHIZUKU_STATUS)} if check_all else {}),
        }
        if check_openminis
        else {"probed": False}
    )
    adb = _adb_status(runtime) if check_adb else {"probed": False}
    scrcpy = _version(runtime, "scrcpy", ("--version",)) if check_scrcpy else {"probed": False}
    tailscale = _tailscale_status(runtime) if check_all else {"probed": False}
    adb_ready = adb.get("identity_match") is True
    openminis_ready = (
        check_openminis
        and _bridge_available(openminis.get("health"))
        and _bridge_available(openminis.get("accessibility"))
    )
    scrcpy_ready = adb_ready and scrcpy.get("installed") is True
    paths: JsonObject
    if target is PreflightTarget.OPENMINIS:
        paths = cast("JsonObject", {"openminis": bool(openminis_ready)})
        checked_paths: list[JsonValue] = ["openminis"]
    elif target is PreflightTarget.ADB:
        paths = cast("JsonObject", {"adb": bool(adb_ready)})
        checked_paths = ["adb"]
    elif target is PreflightTarget.SCRCPY:
        paths = cast(
            "JsonObject",
            {"adb": bool(adb_ready), "scrcpy": bool(scrcpy_ready)},
        )
        checked_paths = ["adb", "scrcpy"]
    else:
        paths = cast(
            "JsonObject",
            {
                "openminis": bool(openminis_ready),
                "scrcpy": bool(scrcpy_ready),
                "adb": bool(adb_ready),
                "shizuku": bool(_shizuku_ready(openminis["shizuku"])),
            },
        )
        checked_paths = ["openminis", "adb", "scrcpy", "shizuku", "tailscale"]
    all_ready = all(value is True for value in paths.values()) and (
        target is not PreflightTarget.ALL or tailscale.get("online") is True
    )
    any_ready = any(value is True for value in paths.values())
    requested_ready = (
        paths.get(target.value) is True if target is not PreflightTarget.ALL else all_ready
    )
    return cast(
        "JsonObject",
        {
            "status": (
                "READY"
                if all_ready
                else "BLOCKED"
                if target is not PreflightTarget.ALL and not requested_ready
                else "DEGRADED"
                if any_ready
                else "BLOCKED"
            ),
            "requested_path": target.value,
            "checked_paths": checked_paths,
            "reuse": {
                "scope": "current_agent_session",
                "persisted": False,
                "invalidate_on": [
                    "device_reboot",
                    "network_change",
                    "bridge_error",
                    "adb_error",
                    "process_death",
                ],
            },
            "openminis": openminis,
            "adb": adb,
            "scrcpy": scrcpy,
            "tailscale": tailscale,
            "control_paths": paths,
            "read_only": True,
        },
    )
