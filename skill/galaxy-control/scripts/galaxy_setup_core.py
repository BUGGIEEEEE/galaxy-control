"""Read-only setup planning and live Galaxy enrollment."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, cast

from galaxy_process import CommandResult, Runner
from galaxy_profile import DeviceProfile, write_profile

TAILSCALE_ADDRESS_PATTERN: Final = re.compile(
    r"\btun[0-9]+\s+inet\s+(100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9.]+)/[0-9]+\b"
)


@dataclass(frozen=True, slots=True)
class SetupError(Exception):
    """Setup diagnosis or enrollment failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class SetupRuntime:
    """Injectable command and executable discovery boundary."""

    runner: Runner
    which: Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class SetupPlan:
    """Exact reviewed local changes and physical user actions."""

    install_commands: tuple[tuple[str, ...], ...]
    user_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ListedDevice:
    """One row from `adb devices -l`."""

    serial: str
    state: str
    transport: str


def _parse_devices(raw: str) -> tuple[ListedDevice, ...]:
    devices: list[ListedDevice] = []
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            transport = "usb" if any(field.startswith("usb:") for field in fields[2:]) else "other"
            devices.append(ListedDevice(fields[0], fields[1], transport))
    return tuple(devices)


def _required_tool(runtime: SetupRuntime, name: str) -> str:
    path = runtime.which(name)
    if path is None:
        raise SetupError(f"{name}_not_installed", f"{name} executable was not found")
    return path


def _run_required(runtime: SetupRuntime, argv: tuple[str, ...], code: str) -> CommandResult:
    result = runtime.runner(argv)
    if not result.succeeded:
        raise SetupError(code, f"reviewed command failed: {argv[-1]}")
    return result


def build_plan(runtime: SetupRuntime) -> SetupPlan:
    """Return exact missing-tool installations without mutating the Mac."""
    brew = runtime.which("brew")
    missing = tuple(name for name in ("adb", "scrcpy", "uv") if runtime.which(name) is None)
    commands: list[tuple[str, ...]] = []
    actions: list[str] = []
    if missing and brew is None:
        actions.append("install_homebrew")
    elif brew is not None:
        for name in missing:
            match name:  # noqa: V001  # noqa: MATCH_OK -- local allowlist values.
                case "adb":
                    commands.append((brew, "install", "--cask", "android-platform-tools"))
                case "scrcpy" | "uv":
                    commands.append((brew, "install", name))
                case unreachable:
                    raise AssertionError(unreachable)
    if runtime.which("tailscale") is None:
        actions.append("install_or_open_tailscale_standalone")
    return SetupPlan(tuple(commands), tuple(actions))


def apply_plan(plan: SetupPlan, runtime: SetupRuntime) -> int:
    """Run only installer argv already selected by the reviewed plan."""
    applied = 0
    for command in plan.install_commands:
        result = runtime.runner(command)
        if not result.succeeded:
            raise SetupError(
                "prerequisite_install_failed",
                f"approved prerequisite installation failed: {command[-1]}",
            )
        applied += 1
    return applied


def enroll(runtime: SetupRuntime, selected_serial: str | None = None) -> DeviceProfile:
    """Enroll exactly one authorized Galaxy from live fixed ADB identity reads."""
    adb = _required_tool(runtime, "adb")
    listing = _run_required(runtime, (adb, "devices", "-l"), "adb_devices_failed")
    devices = _parse_devices(listing.stdout)
    if not devices:
        raise SetupError("adb_no_device", "no adb device is connected")
    if selected_serial is None:
        if len(devices) > 1:
            raise SetupError(
                "adb_multiple_devices", "multiple adb devices require explicit isolation"
            )
        device = next(iter(devices))
    else:
        selected = tuple(device for device in devices if device.serial == selected_serial)
        if len(selected) != 1:
            raise SetupError("device_not_listed", "selected serial is not one unique live device")
        device = next(iter(selected))
    match device.state:  # noqa: V001  # noqa: MATCH_OK -- live ADB state is open.
        case "device":
            pass
        case "unauthorized":
            raise SetupError("adb_unauthorized", "the Galaxy is unauthorized")
        case "offline":
            raise SetupError("adb_offline", "the Galaxy is offline")
        case _:
            raise SetupError("adb_device_unavailable", "the Galaxy is unavailable")
    if device.transport != "usb":
        raise SetupError("usb_required", "enrollment requires one physically connected Galaxy")
    prefix = (adb, "-s", device.serial, "shell")
    serial = _run_required(runtime, (*prefix, "getprop", "ro.serialno"), "serial_unavailable")
    model = _run_required(runtime, (*prefix, "getprop", "ro.product.model"), "model_unavailable")
    address = _run_required(
        runtime,
        (*prefix, "ip", "-o", "-4", "addr", "show"),
        "tailscale_address_unavailable",
    )
    physical_serial = serial.stdout.strip()
    if physical_serial != device.serial:
        raise SetupError("device_mismatch", "listed and physical serial do not match")
    expected_model = model.stdout.strip().replace("-", "_")
    matches = TAILSCALE_ADDRESS_PATTERN.findall(address.stdout)
    if not matches:
        raise SetupError("tailscale_address_unavailable", "Galaxy tailnet address was not found")
    if len(matches) != 1:
        raise SetupError(
            "tailscale_address_ambiguous",
            "Galaxy has multiple candidate tailnet tunnel addresses",
        )
    profile = DeviceProfile(
        schema=1,
        physical_serial=physical_serial,
        expected_model=expected_model,
        tailscale_ipv4=cast("str", matches[0]),
        openminis_port=43129,
        steady_adb_enabled=False,
    )
    _ = write_profile(profile)
    return profile
