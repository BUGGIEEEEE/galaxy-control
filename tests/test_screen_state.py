from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_screen_core import ScreenError
from galaxy_screen_state import (
    ProcessIdentity,
    ScreenState,
    identity_matches,
    load_state,
    write_state,
)


def state() -> ScreenState:
    argv = (
        "/private/cache/Galaxy Control Scrcpy.app/Contents/MacOS/scrcpy",
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
        executable=argv[0],
        argv=argv,
        ps_start="Mon Aug 10 12:00:00 2026",
        ps_command=" ".join(argv),
        stderr_path="/private/cache/scrcpy-SESSION.stderr",
        output_path=None,
        record_work_dir=None,
        record_temp_path=None,
    )


def test_state_round_trip_is_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("GALAXY_SCREEN_STATE_DIR", str(tmp_path / "screen"))

    # When
    write_state(state())
    loaded = load_state()

    # Then
    assert loaded == state()
    path = tmp_path / "screen" / "scrcpy-session.json"
    assert path.stat().st_mode & 0o777 == 0o600


def test_state_rejects_world_readable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("GALAXY_SCREEN_STATE_DIR", str(tmp_path / "screen"))
    write_state(state())
    path = tmp_path / "screen" / "scrcpy-session.json"
    path.chmod(0o644)

    # When / Then
    with pytest.raises(ScreenError, match="trustworthy"):
        load_state()


def test_identity_matches_only_exact_owned_process() -> None:
    # Given
    stored = state()
    exact = ProcessIdentity(stored.ps_start, stored.ps_command)
    different = ProcessIdentity(stored.ps_start, stored.ps_command.replace("SESSION", "OTHER"))

    # When / Then
    assert identity_matches(stored, exact) is True
    assert identity_matches(stored, different) is False
