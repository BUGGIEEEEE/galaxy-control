from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_adb import AdbDevice, AdbRuntime
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_screen import execute, route_for_action
from galaxy_screen_core import ScreenError, build_scrcpy_argv, parse_request, select_device
from galaxy_screen_session import REQUIRED_OPTIONS, ScreenRuntime

BOOT_ID = "11111111-2222-3333-4444-555555555555"


def profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=False,
    )


def device(serial: str = "DEMO123456", state: str = "device", model: str = "SM_S921B") -> AdbDevice:
    transport = "tcpip" if ":" in serial else "usb"
    return AdbDevice(serial, state, transport, model)


def verified_identity_response(argv: tuple[str, ...]) -> CommandResult | None:
    if argv[-1:] == ("get-state",):
        return CommandResult(0, "device\n", "")
    if argv[-2:] == ("getprop", "ro.serialno"):
        return CommandResult(0, "DEMO123456\n", "")
    if argv[-2:] == ("getprop", "ro.product.model"):
        return CommandResult(0, "SM-S921B\n", "")
    if argv[-2:] == ("cat", "/proc/sys/kernel/random/boot_id"):
        return CommandResult(0, f"{BOOT_ID}\n", "")
    return None


VERIFIED_IDENTITY_CALLS = [
    ("/opt/homebrew/bin/adb", "-s", "DEMO123456", "get-state"),
    (
        "/opt/homebrew/bin/adb",
        "-s",
        "DEMO123456",
        "shell",
        "getprop",
        "ro.serialno",
    ),
    (
        "/opt/homebrew/bin/adb",
        "-s",
        "DEMO123456",
        "shell",
        "getprop",
        "ro.product.model",
    ),
    (
        "/opt/homebrew/bin/adb",
        "-s",
        "DEMO123456",
        "shell",
        "cat",
        "/proc/sys/kernel/random/boot_id",
    ),
]


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
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        calls.append(argv)
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\n"
                "UNRELATED device model:SM_OTHER usb:2-1\n"
                "DEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(
                0,
                "--serial --no-control --no-audio --no-clipboard-autosync "
                "--record --no-playback --window-title",
                "",
            )
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")
    runtime = ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner)

    # When
    envelope, exit_code = execute(("doctor",), runtime)

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is True
    assert envelope["result"]["launch_verified"] is False
    assert envelope["result"]["adb"]["ready"] is True
    assert envelope["result"]["adb"]["selected_serial"] == "DEMO123456"
    assert envelope["result"]["scrcpy"]["options_supported"] is True
    assert calls == [
        ("/opt/homebrew/bin/adb", "devices", "-l"),
        *VERIFIED_IDENTITY_CALLS,
        ("/opt/homebrew/bin/scrcpy", "--help"),
    ]
    assert envelope["result"]["route"] == {
        "controller": "scrcpy",
        "transport": "adb",
        "role": "observe",
        "verification_required": False,
        "verify_with": [],
    }


def test_scrcpy_doctor_rejects_unenrolled_adb_device() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nUNRELATED device model:SM_OTHER usb:2-1\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["adb"]["ready"] is False
    assert envelope["result"]["adb"]["error"] == "adb_no_device"
    assert envelope["result"]["launch_verified"] is False


def test_scrcpy_doctor_rejects_disabled_fixed_tcp_transport() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\n100.64.1.20:5555 device model:SM_S921B\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        raise AssertionError(argv)

    disabled_profile = profile().model_copy(update={"steady_adb_enabled": False})
    adb = AdbRuntime(disabled_profile, "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["adb"]["ready"] is False
    assert envelope["result"]["adb"]["error"] == "adb_no_device"


def test_scrcpy_doctor_rejects_dynamic_transport_for_steady_profile() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\n100.64.1.20:32002 device model:SM_S921B\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        raise AssertionError(argv)

    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})
    adb = AdbRuntime(steady_profile, "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["adb"]["ready"] is False
    assert envelope["result"]["adb"]["error"] == "adb_no_device"


def test_scrcpy_doctor_rejects_usb_transport_for_steady_profile() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        raise AssertionError(argv)

    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})
    adb = AdbRuntime(steady_profile, "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["adb"]["ready"] is False
    assert envelope["result"]["adb"]["error"] == "adb_no_device"


def test_scrcpy_doctor_accepts_fixed_transport_for_steady_profile() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\n100.64.1.20:5555 device model:SM_S921B\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})
    adb = AdbRuntime(steady_profile, "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is True
    assert envelope["result"]["adb"]["ready"] is True


def test_scrcpy_doctor_reports_missing_safe_option_without_launching() -> None:
    # Given
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        calls.append(argv)
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, "--serial --no-control", "")
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["scrcpy"]["options_supported"] is False
    assert envelope["result"]["launch_verified"] is False
    assert calls == [
        ("/opt/homebrew/bin/adb", "devices", "-l"),
        *VERIFIED_IDENTITY_CALLS,
        ("/opt/homebrew/bin/scrcpy", "--help"),
    ]


def test_scrcpy_doctor_does_not_accept_prefixed_option_name() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(
                0,
                "--serial --no-control --no-audio --no-clipboard-autosync "
                "--record-format --no-playback --window-title",
                "",
            )
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["scrcpy"]["options_supported"] is False


def test_scrcpy_doctor_rereads_physical_identity_before_ready() -> None:
    # Given
    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        if argv[-2:] == ("devices", "-l"):
            return CommandResult(
                0,
                "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
                "",
            )
        if argv[-2:] == ("DEMO123456", "get-state"):
            return CommandResult(0, "device\n", "")
        if argv[-2:] == ("getprop", "ro.serialno"):
            return CommandResult(0, "OTHER123456\n", "")
        if argv == ("/opt/homebrew/bin/scrcpy", "--help"):
            return CommandResult(0, " ".join(REQUIRED_OPTIONS), "")
        identity = verified_identity_response(argv)
        if identity is not None:
            return identity
        raise AssertionError(argv)

    adb = AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: "")

    # When
    envelope, exit_code = execute(
        ("doctor",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 0
    assert envelope["result"]["preflight_ready"] is False
    assert envelope["result"]["adb"]["ready"] is False
    assert envelope["result"]["adb"]["error"] == "device_mismatch"


def test_scrcpy_record_route_reports_recording_role() -> None:
    # Given
    route = route_for_action("record", {"verification_required": False})

    # When / Then
    assert route.role == "record"
