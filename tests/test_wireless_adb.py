from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_remote_adb import AdbRuntime, execute

BOOT_ID = "11111111-2222-3333-4444-555555555555"


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        self.calls.append((argv, stdin))
        return self.responses.pop(0)


def result(stdout: str = "", returncode: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(returncode, stdout, stderr)


def profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=True,
    )


def runtime(runner: FakeRunner, code: str = "123456") -> AdbRuntime:
    return AdbRuntime(profile(), "/opt/homebrew/bin/adb", runner, lambda: code)


def identity_results() -> list[CommandResult]:
    return [
        result("device\n"),
        result("DEMO123456\n"),
        result("SM-S921B\n"),
        result(f"{BOOT_ID}\n"),
    ]


@pytest.mark.parametrize("port", ["0", "65536", "-1", " 32001", "32:001", "32001;id", "5555"])
def test_wireless_connection_port_rejects_invalid_value(port: str) -> None:
    # Given / When
    envelope, exit_code = execute(("wireless-connect", "--port", port), runtime(FakeRunner([])))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "connection_port_invalid"


def test_wireless_pair_passes_code_only_through_stdin() -> None:
    # Given
    runner = FakeRunner([result("Successfully paired\n")])

    # When
    envelope, exit_code = execute(
        ("wireless-pair", "--port", "32001", "--approved"), runtime(runner)
    )

    # Then
    assert exit_code == 0
    assert runner.calls == [(("/opt/homebrew/bin/adb", "pair", "100.64.1.20:32001"), "123456\n")]
    assert "123456" not in str(envelope)


def test_wireless_pair_rejects_invalid_code_before_adb_call() -> None:
    # Given
    runner = FakeRunner([])

    # When
    envelope, exit_code = execute(
        ("wireless-pair", "--port", "32001", "--approved"), runtime(runner, "12 456")
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "pair_code_invalid"
    assert runner.calls == []


def test_wireless_connect_verifies_identity_and_writes_private_boot_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner([result("connected\n"), *identity_results()])

    # When
    envelope, exit_code = execute(("wireless-connect", "--port", "32002"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["endpoint"] == "100.64.1.20:32002"
    state_path = tmp_path / "state" / "wireless-session.json"
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert BOOT_ID not in state_path.read_text()


def test_legacy_enable_requires_same_cached_endpoint_and_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    connect_runner = FakeRunner([result("connected\n"), *identity_results()])
    _, connect_code = execute(("wireless-connect", "--port", "32002"), runtime(connect_runner))
    assert connect_code == 0
    enable_runner = FakeRunner([*identity_results(), result("restarting in TCP mode port: 5555\n")])

    # When
    envelope, exit_code = execute(
        ("legacy-enable-from-wireless", "--port", "32002", "--approved"),
        runtime(enable_runner),
    )

    # Then
    assert exit_code == 0
    assert enable_runner.calls[-1][0] == (
        "/opt/homebrew/bin/adb",
        "-s",
        "100.64.1.20:32002",
        "tcpip",
        "5555",
    )
    assert envelope["result"]["verification_required"] is True


def test_wireless_recover_refuses_previous_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    connect_runner = FakeRunner([result("connected\n"), *identity_results()])
    _, connect_code = execute(("wireless-connect", "--port", "32002"), runtime(connect_runner))
    assert connect_code == 0
    changed_boot = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    recover_runner = FakeRunner(
        [
            result("connected\n"),
            result("device\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(f"{changed_boot}\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-recover", "--port", "32002"), runtime(recover_runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "boot_session_mismatch"
