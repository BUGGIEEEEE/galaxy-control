"""Pure request, device-selection, and argv logic for fixed scrcpy profiles."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, NoReturn, assert_never

from galaxy_adb import AdbDevice, normalize_model
from galaxy_profile import DeviceProfile

ScreenProfile = Literal["view", "control", "record"]
ScreenAction = Literal["doctor", "view", "control", "record", "stop"]
SERIAL_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ALLOWED_RECORD_SUFFIXES: Final = frozenset((".mp4", ".mkv"))
SESSION_PREFIX: Final = "Galaxy Control "


@dataclass(frozen=True, slots=True)
class ScreenError(Exception):
    """Stable scrcpy profile failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ScreenRequest:
    action: ScreenAction
    serial: str | None = None
    output: Path | None = None


def _raise(code: str, message: str) -> NoReturn:
    raise ScreenError(code, message)


def validate_serial(raw: str) -> str:
    """Accept one bounded ADB serial token, never an option or shell fragment."""
    if SERIAL_PATTERN.fullmatch(raw) is None:
        _raise("invalid_request", "serial is invalid")
    return raw


def validate_output(raw: str) -> Path:
    """Require a new absolute recording target with a supported container."""
    if "\x00" in raw or len(os.fsencode(raw)) > 4096:
        _raise("record_path_invalid", "record output path is invalid")
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.suffix.lower() not in ALLOWED_RECORD_SUFFIXES:
        _raise("record_path_invalid", "record output must be an absolute .mp4 or .mkv path")
    if os.path.lexists(candidate):
        _raise("record_target_exists", "record output already exists")
    try:
        parent = candidate.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ScreenError("record_path_invalid", "record output parent does not exist") from error
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        _raise("record_path_invalid", "record output parent is not writable")
    return parent / candidate.name


def parse_request(argv: tuple[str, ...]) -> ScreenRequest:
    """Parse one exact scrcpy profile without passthrough flags."""
    match argv:  # noqa: V001  # noqa: MATCH_OK -- open tuple rejects unknown forms.
        case ("doctor",):
            return ScreenRequest("doctor")
        case ("view",):
            return ScreenRequest("view")
        case ("view", "--serial", raw):
            return ScreenRequest("view", validate_serial(raw))
        case ("control",):
            return ScreenRequest("control")
        case ("control", "--serial", raw):
            return ScreenRequest("control", validate_serial(raw))
        case ("record", "--output", raw):
            return ScreenRequest("record", output=validate_output(raw))
        case ("record", "--output", raw, "--serial", serial):
            return ScreenRequest("record", validate_serial(serial), validate_output(raw))
        case ("record", "--serial", serial, "--output", raw):
            return ScreenRequest("record", validate_serial(serial), validate_output(raw))
        case ("stop",):
            return ScreenRequest("stop")
        case _:
            _raise("invalid_request", "unsupported scrcpy command or option")


def _serial_matches(profile: DeviceProfile, serial: str) -> bool:
    return serial in {profile.physical_serial, profile.steady_endpoint} or serial.startswith(
        (f"{profile.tailscale_ipv4}:", f"adb-{profile.physical_serial}-")
    )


def select_device(
    profile: DeviceProfile,
    devices: tuple[AdbDevice, ...],
    requested_serial: str | None,
) -> AdbDevice:
    """Select only one enrolled, available, model-matching device."""
    if not devices:
        _raise("adb_no_device", "no ADB device is connected")
    if requested_serial is None:
        if len(devices) > 1:
            _raise("adb_multiple_devices", "multiple ADB devices require --serial")
        selected = next(iter(devices))
    else:
        matches = tuple(device for device in devices if device.serial == requested_serial)
        if len(matches) != 1:
            _raise("adb_no_device", "requested ADB serial is not connected")
        selected = next(iter(matches))
    if not _serial_matches(profile, selected.serial):
        _raise("device_mismatch", "selected ADB device is not the enrolled Galaxy")
    match selected.state:  # noqa: V001  # noqa: MATCH_OK -- live ADB state is open.
        case "device":
            pass
        case "unauthorized":
            _raise("adb_unauthorized", "selected Galaxy is unauthorized")
        case "offline":
            _raise("adb_offline", "selected Galaxy is offline")
        case _:
            _raise("adb_device_unavailable", "selected Galaxy is unavailable")
    if normalize_model(selected.model or "") != profile.expected_model:
        _raise("device_mismatch", "selected Galaxy model does not match the profile")
    return selected


def build_scrcpy_argv(
    executable: str,
    profile: ScreenProfile,
    serial: str,
    session_id: str,
    record_temp_path: Path | None = None,
) -> tuple[str, ...]:
    """Build one immutable fixed-profile scrcpy argv tuple."""
    base = (
        executable,
        "--serial",
        serial,
        "--no-audio",
        "--no-clipboard-autosync",
        f"--window-title={SESSION_PREFIX}{session_id}",
    )
    match profile:
        case "view":
            return (*base, "--no-control")
        case "control":
            return base
        case "record":
            if record_temp_path is None:
                _raise("record_path_invalid", "record temp path is required")
            return (*base, "--no-control", f"--record={record_temp_path}", "--no-playback")
        case unreachable:
            assert_never(unreachable)
