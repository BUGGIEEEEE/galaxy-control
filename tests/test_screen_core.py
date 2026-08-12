from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_adb import AdbDevice, AdbRuntime
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_screen import execute, route_for_action
from galaxy_screen_core import ScreenError, build_scrcpy_argv, parse_request, select_device
from galaxy_screen_session import ScreenRuntime


def profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=True,
    )


def device(serial: str = "DEMO123456", state: str = "device", model: str = "SM_S921B") -> AdbDevice:
    transport = "tcpip" if ":" in serial else "usb"
    return AdbDevice(serial, state, transport, model)


def test_view_argv_has_all_read_only_options() -> None:
    # Given / When
    argv = build_scrcpy_argv("/opt/homebrew/bin/scrcpy", "view", "DEMO123456", "SESSION")

    # Then
    assert "--no-control" in argv
    assert "--no-audio" in argv
    assert "--no-clipboard-autosync" in argv
    assert argv[1:3] == ("--serial", "DEMO123456")


def test_control_argv_enables_control_but_disables_audio_and_clipboard() -> None:
    # Given / When
    argv = build_scrcpy_argv("/opt/homebrew/bin/scrcpy", "control", "DEMO123456", "SESSION")

    # Then
    assert "--no-control" not in argv
    assert "--no-audio" in argv
    assert "--no-clipboard-autosync" in argv


def test_record_argv_disables_control_audio_and_playback(tmp_path: Path) -> None:
    # Given
    target = tmp_path / "capture.mp4"

    # When
    argv = build_scrcpy_argv(
        "/opt/homebrew/bin/scrcpy",
        "record",
        "DEMO123456",
        "SESSION",
        target,
    )

    # Then
    assert "--no-control" in argv
    assert "--no-audio" in argv
    assert "--no-playback" in argv
    assert f"--record={target}" in argv


@pytest.mark.parametrize(
    "argv",
    [
        ("view", "--serial", "-d"),
        ("view", "--serial", "DEMO;touch"),
        ("view", "--turn-screen-off"),
        ("control", "--tcpip", "example.invalid"),
        ("record", "--output", "relative.mp4"),
        ("stop", "--serial", "DEMO123456"),
    ],
)
def test_parse_rejects_injection_and_passthrough_options(argv: tuple[str, ...]) -> None:
    # Given / When / Then
    with pytest.raises(ScreenError):
        parse_request(argv)


def test_record_rejects_existing_target(tmp_path: Path) -> None:
    # Given
    target = tmp_path / "capture.mp4"
    target.write_bytes(b"existing")

    # When / Then
    with pytest.raises(ScreenError) as captured:
        parse_request(("record", "--output", str(target)))
    assert captured.value.code == "record_target_exists"


def test_select_refuses_multiple_devices_without_serial() -> None:
    # Given
    devices = (device(), device("100.64.1.20:5555"))

    # When / Then
    with pytest.raises(ScreenError) as captured:
        select_device(profile(), devices, None)
    assert captured.value.code == "adb_multiple_devices"


@pytest.mark.parametrize(
    ("state", "code"),
    [("unauthorized", "adb_unauthorized"), ("offline", "adb_offline")],
)
def test_select_classifies_unavailable_device(state: str, code: str) -> None:
    # Given / When / Then
    with pytest.raises(ScreenError) as captured:
        select_device(profile(), (device(state=state),), None)
    assert captured.value.code == code


def test_select_rejects_model_mismatch() -> None:
    # Given / When / Then
    with pytest.raises(ScreenError) as captured:
        select_device(profile(), (device(model="SM_OTHER"),), None)
    assert captured.value.code == "device_mismatch"


def test_scrcpy_doctor_payload_identifies_adb_transport() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")
    runtime = ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner)

    # When
    envelope, exit_code = execute(("doctor",), runtime)

    # Then
    assert exit_code == 0
    assert envelope["result"]["route"] == {
        "controller": "scrcpy",
        "transport": "adb",
        "role": "observe",
        "verification_required": False,
        "verify_with": [],
    }


def test_scrcpy_record_route_reports_recording_role() -> None:
    # Given
    route = route_for_action("record", {"verification_required": False})

    # When / Then
    assert route.role == "record"
