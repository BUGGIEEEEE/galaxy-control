from __future__ import annotations

import os
from pathlib import Path

import pytest

import galaxy_screen_session
from galaxy_recording import finalize_recording, prepare_recording
from galaxy_screen_core import ScreenError
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
