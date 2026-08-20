from __future__ import annotations

import os
from pathlib import Path

import pytest

import galaxy_screen_session
from galaxy_adb import AdbRuntime
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_recording import finalize_recording, prepare_recording
from galaxy_screen import execute
from galaxy_screen_core import ScreenError
from galaxy_screen_session import REQUIRED_OPTIONS, ScreenRuntime
from galaxy_screen_state import ProcessIdentity, ScreenState, write_state


def managed_state(tmp_path: Path) -> ScreenState:
    executable = str(tmp_path / "Galaxy Control Scrcpy.app" / "Contents" / "MacOS" / "scrcpy")
    argv = (
        executable,
        "--serial",
        "DEMO123456",
        "--window-title=Galaxy Control SESSION",
    )
    return ScreenState(
        schema_version=1,
        session_id="SESSION",
        pid=1234,
        profile="control",
        serial="DEMO123456",
        model="SM_S921B",
        executable=executable,
        argv=argv,
        ps_start="Mon Aug 10 12:00:00 2026",
        ps_command=" ".join(argv),
        stderr_path=str(tmp_path / "scrcpy-SESSION.stderr"),
        output_path=None,
        record_work_dir=None,
        record_temp_path=None,
    )


def test_start_reverifies_identity_before_launching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    profile = DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=False,
    )
    responses = [
        CommandResult(
            0,
            "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
            "",
        ),
        CommandResult(0, "device\n", ""),
        CommandResult(0, "OTHER123456\n", ""),
        CommandResult(0, "SM-S921B\n", ""),
    ]

    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        return responses.pop(0)

    adb = AdbRuntime(profile, "/opt/homebrew/bin/adb", runner, lambda: "")
    monkeypatch.setattr(
        galaxy_screen_session.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("scrcpy must not launch before identity verification")
        ),
    )

    # When
    envelope, exit_code = execute(
        ("view",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "device_mismatch"


def test_start_rejects_prefixed_scrcpy_option_before_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    profile = DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
    )
    boot_id = "11111111-2222-3333-4444-555555555555"
    responses = [
        CommandResult(
            0,
            "List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n",
            "",
        ),
        CommandResult(0, "device\n", ""),
        CommandResult(0, "DEMO123456\n", ""),
        CommandResult(0, "SM-S921B\n", ""),
        CommandResult(0, f"{boot_id}\n", ""),
        CommandResult(
            0,
            " ".join(
                option if option != "--record" else "--record-format" for option in REQUIRED_OPTIONS
            ),
            "",
        ),
    ]

    def runner(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        assert stdin is None
        return responses.pop(0)

    adb = AdbRuntime(profile, "/opt/homebrew/bin/adb", runner, lambda: "")
    monkeypatch.setattr(
        galaxy_screen_session.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("scrcpy must not launch with unsupported options")
        ),
    )

    # When
    envelope, exit_code = execute(
        ("view",),
        ScreenRuntime(adb, "/opt/homebrew/bin/scrcpy", runner),
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "scrcpy_option_unsupported"


def test_stop_refuses_unmanaged_process_without_signalling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_SCREEN_STATE_DIR", str(tmp_path / "state"))
    state = managed_state(tmp_path)
    write_state(state)
    monkeypatch.setattr(
        galaxy_screen_session,
        "process_identity",
        lambda _pid: ProcessIdentity(state.ps_start, "/usr/bin/unrelated"),
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append((pid, sig)))

    # When / Then
    with pytest.raises(ScreenError) as captured:
        galaxy_screen_session.stop()
    assert captured.value.code == "process_identity_mismatch"
    assert signals == []


def test_finalize_mp4_requires_valid_nonempty_container(tmp_path: Path) -> None:
    # Given
    output = tmp_path / "capture.mp4"
    paths = prepare_recording(output)
    assert paths is not None
    paths.temp_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"payload")

    # When
    result = finalize_recording(paths)

    # Then
    assert result["path"] == str(output)
    assert result["header_valid"] is True
    assert output.is_file()


def test_finalize_rejects_invalid_container(tmp_path: Path) -> None:
    # Given
    output = tmp_path / "capture.mkv"
    paths = prepare_recording(output)
    assert paths is not None
    paths.temp_path.write_bytes(b"not-a-container")

    # When / Then
    with pytest.raises(ScreenError) as captured:
        finalize_recording(paths)
    assert captured.value.code == "scrcpy_record_failed"


def test_source_contains_no_broad_process_kill() -> None:
    # Given
    source = Path(galaxy_screen_session.__file__).read_text()

    # When / Then
    assert "killall" not in source
    assert "pkill" not in source
    assert "shell=True" not in source
