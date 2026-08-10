"""Read-only, partial Galaxy Control diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
        and device.serial == runtime.profile.physical_serial
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


def inspect_device(runtime: DoctorRuntime) -> JsonObject:
    """Combine independent read-only paths without hiding partial failures."""
    openminis: JsonObject = {
        "health": _bridge_status(runtime, Action.HEALTH),
        "accessibility": _bridge_status(runtime, Action.A11Y_STATUS),
        "shizuku": _bridge_status(runtime, Action.SHIZUKU_STATUS),
    }
    adb = _adb_status(runtime)
    scrcpy = _version(runtime, "scrcpy", ("--version",))
    tailscale = _tailscale_status(runtime)
    adb_ready = adb.get("identity_match") is True
    openminis_ready = _bridge_available(openminis["health"]) and _bridge_available(
        openminis["accessibility"]
    )
    paths: JsonObject = {
        "openminis": openminis_ready,
        "scrcpy": adb_ready and scrcpy.get("installed") is True,
        "adb": adb_ready,
        "shizuku": _shizuku_ready(openminis["shizuku"]),
    }
    all_ready = all(value is True for value in paths.values()) and tailscale.get("online") is True
    any_ready = any(value is True for value in paths.values())
    return {
        "status": "READY" if all_ready else "DEGRADED" if any_ready else "BLOCKED",
        "openminis": openminis,
        "adb": adb,
        "scrcpy": scrcpy,
        "tailscale": tailscale,
        "control_paths": paths,
        "read_only": True,
    }
