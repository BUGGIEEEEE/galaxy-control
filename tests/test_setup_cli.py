from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile, load_profile, write_profile
from galaxy_setup import execute
from galaxy_setup_core import SetupRuntime


class FakeRunner:
    def __init__(self, responses: list[CommandResult] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        self.calls.append(argv)
        assert stdin is None
        return self.responses.pop(0)


def ready_runtime(runner: FakeRunner | None = None) -> SetupRuntime:
    paths = {
        "brew": "/opt/homebrew/bin/brew",
        "adb": "/opt/homebrew/bin/adb",
        "scrcpy": "/opt/homebrew/bin/scrcpy",
        "uv": "/opt/homebrew/bin/uv",
        "tailscale": "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    }
    return SetupRuntime(runner=runner or FakeRunner(), which=paths.get)


def test_plan_envelope_reports_ready_when_all_tools_exist() -> None:
    # Given / When
    envelope, exit_code = execute(("plan",), ready_runtime())

    # Then
    assert exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["status"] == "READY"
    assert envelope["result"]["install_commands"] == []


def test_apply_requires_explicit_approval() -> None:
    # Given / When
    envelope, exit_code = execute(("apply",), ready_runtime())

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "approval_required"


def test_show_profile_redacts_serial_and_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    _ = write_profile(
        DeviceProfile(
            schema=1,
            physical_serial="DEMO123456",
            expected_model="SM_S921B",
            tailscale_ipv4="100.64.1.20",
            openminis_port=43129,
            steady_adb_enabled=False,
        )
    )

    # When
    envelope, exit_code = execute(("show-profile",), ready_runtime())

    # Then
    encoded = str(envelope)
    assert exit_code == 0
    assert "DEMO123456" not in encoded
    assert "100.64.1.20" not in encoded
    assert envelope["result"]["expected_model"] == "SM_S921B"


def test_enroll_requires_approval_before_adb_call() -> None:
    # Given
    runner = FakeRunner()

    # When
    envelope, exit_code = execute(("enroll",), ready_runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "approval_required"
    assert runner.calls == []


def test_unknown_option_is_rejected() -> None:
    # Given / When
    envelope, exit_code = execute(("plan", "--host", "example.invalid"), ready_runtime())

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "invalid_request"


def test_enroll_serial_form_is_strictly_shaped() -> None:
    # Given / When
    envelope, exit_code = execute(
        ("enroll", "--serial", "DEMO123456", "--approved", "--extra"), ready_runtime()
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("command", "enabled"),
    [("enable-steady-adb", True), ("disable-steady-adb", False)],
)
def test_steady_adb_preference_requires_approval_and_updates_private_profile(
    command: str,
    enabled: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    _ = write_profile(
        DeviceProfile(
            schema=1,
            physical_serial="DEMO123456",
            expected_model="SM_S921B",
            tailscale_ipv4="100.64.1.20",
            steady_adb_enabled=not enabled,
        )
    )

    # When
    denied, denied_code = execute((command,), ready_runtime())
    envelope, exit_code = execute((command, "--approved"), ready_runtime())

    # Then
    assert denied_code == 1
    assert denied["error"]["code"] == "approval_required"
    assert exit_code == 0
    assert envelope["result"]["steady_adb_enabled"] is enabled
    assert load_profile().steady_adb_enabled is enabled
