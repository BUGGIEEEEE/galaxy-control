"""Shared typed ADB identity and device-list operations."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from galaxy_process import CommandResult, Runner
from galaxy_profile import DeviceProfile


@dataclass(frozen=True, slots=True)
class AdbError(Exception):
    """Stable ADB adapter failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class AdbRuntime:
    """Enrolled profile and injectable ADB boundaries."""

    profile: DeviceProfile
    adb_path: str | None
    runner: Runner
    pair_code_reader: Callable[[], str]


@dataclass(frozen=True, slots=True)
class AdbDevice:
    serial: str
    state: str
    transport: str
    model: str | None


@dataclass(frozen=True, slots=True)
class VerifiedDevice:
    endpoint: str
    physical_serial: str
    model: str
    boot_session_hash: str | None = None


def normalize_model(raw: str) -> str:
    """Normalize Android's hyphenated and underscored model forms."""
    return raw.strip().replace("-", "_")


def adb_path(runtime: AdbRuntime) -> str:
    """Require an installed ADB executable."""
    if runtime.adb_path is None:
        raise AdbError("adb_not_installed", "adb executable was not found")
    return runtime.adb_path


def run_adb(
    runtime: AdbRuntime, argv: tuple[str, ...], *, stdin: str | None = None
) -> CommandResult:
    """Run one reviewed ADB argv tuple."""
    result = runtime.runner(argv, stdin=stdin)
    if result.returncode == 127:
        raise AdbError("adb_not_installed", "adb executable could not be started")
    return result


def parse_devices(raw: str) -> tuple[AdbDevice, ...]:
    """Parse `adb devices -l` without guessing missing metadata."""
    devices: list[AdbDevice] = []
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2:
            continue
        attributes = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
        transport = "tcpip" if ":" in fields[0] or fields[0].startswith("adb-") else "usb"
        devices.append(AdbDevice(fields[0], fields[1], transport, attributes.get("model")))
    return tuple(devices)


def list_devices(runtime: AdbRuntime) -> tuple[AdbDevice, ...]:
    """Read the current ADB device list."""
    result = run_adb(runtime, (adb_path(runtime), "devices", "-l"))
    if not result.succeeded:
        raise AdbError("adb_devices_failed", "adb devices failed")
    return parse_devices(result.stdout)


def _state_error(result: CommandResult) -> AdbError:
    combined = f"{result.stdout}\n{result.stderr}".lower()
    if "unauthorized" in combined:
        return AdbError("adb_unauthorized", "the Galaxy is unauthorized")
    if "offline" in combined:
        return AdbError("adb_offline", "the Galaxy is offline")
    return AdbError("adb_no_device", "the Galaxy is unavailable")


def verify_endpoint(runtime: AdbRuntime, endpoint: str, *, include_boot: bool) -> VerifiedDevice:
    """Verify live state, physical serial, model, and optional boot identity."""
    adb = adb_path(runtime)
    state = run_adb(runtime, (adb, "-s", endpoint, "get-state"))
    if not state.succeeded or state.stdout.strip() != "device":
        raise _state_error(state)
    serial = run_adb(runtime, (adb, "-s", endpoint, "shell", "getprop", "ro.serialno"))
    model = run_adb(runtime, (adb, "-s", endpoint, "shell", "getprop", "ro.product.model"))
    if (
        not serial.succeeded
        or not model.succeeded
        or serial.stdout.strip() != runtime.profile.physical_serial
        or normalize_model(model.stdout) != runtime.profile.expected_model
    ):
        raise AdbError(
            "device_mismatch", "ADB endpoint identity does not match the enrolled Galaxy"
        )
    boot_hash: str | None = None
    if include_boot:
        boot = run_adb(
            runtime,
            (adb, "-s", endpoint, "shell", "cat", "/proc/sys/kernel/random/boot_id"),
        )
        boot_id = boot.stdout.strip()
        try:
            parsed_boot_id = uuid.UUID(boot_id)
        except ValueError:
            parsed_boot_id = None
        if not boot.succeeded or parsed_boot_id is None or str(parsed_boot_id) != boot_id.lower():
            raise AdbError("boot_session_unavailable", "boot session could not be verified")
        boot_hash = hashlib.sha256(str(parsed_boot_id).encode()).hexdigest()
    return VerifiedDevice(
        endpoint, serial.stdout.strip(), runtime.profile.expected_model, boot_hash
    )
