from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_remote_adb import AdbRuntime, execute
from galaxy_remote_adb_wireless import parse_mdns_connection_ports

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
        auto_reconnect_adb_enabled=True,
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


def test_mdns_parser_returns_only_enrolled_connect_service_ports() -> None:
    # Given
    output = (
        "List of discovered mdns services\n"
        "adb-OTHER-a1 _adb-tls-connect._tcp. 192.168.1.30:31000\n"
        "adb-DEMO123456-pair _adb-tls-pairing._tcp. 192.168.1.20:32001\n"
        "adb-DEMO123456-live _adb-tls-connect._tcp. 192.168.1.20:32002\n"
        "adb-DEMO123456-live _adb-tls-connect._tcp. [fe80::1]:32002\n"
    )

    # When
    ports = parse_mdns_connection_ports(output, "DEMO123456")

    # Then
    assert ports == (32002,)


def test_mdns_parser_rejects_malformed_matching_service_rows() -> None:
    # Given
    output = (
        "List of discovered mdns services\n"
        "adb-DEMO123456-a _adb-tls-connect._tcp. missing-port\n"
        "adb-DEMO123456-b _adb-tls-connect._tcp. 192.168.1.20:5555\n"
        "adb-DEMO123456-c _adb-tls-connect._tcp. 192.168.1.20:70000\n"
        "adb-DEMO123456evil-d _adb-tls-connect._tcp. 192.168.1.20:32002\n"
    )

    # When / Then
    assert parse_mdns_connection_ports(output, "DEMO123456") == ()


def test_mdns_parser_preserves_distinct_matching_ports_for_ambiguity_check() -> None:
    # Given
    output = (
        "List of discovered mdns services\n"
        "adb-DEMO123456-a _adb-tls-connect._tcp 192.168.1.20:32002\n"
        "adb-DEMO123456-b _adb-tls-connect._tcp. 192.168.1.20:32003\n"
    )

    # When / Then
    assert parse_mdns_connection_ports(output, "DEMO123456") == (32002, 32003)


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


def test_wireless_prepare_requires_current_request_approval() -> None:
    # Given
    runner = FakeRunner([])

    # When
    envelope, exit_code = execute(("wireless-prepare",), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "approval_required"
    assert runner.calls == []


def test_wireless_prepare_requires_persisted_auto_reconnect_opt_in() -> None:
    # Given
    disabled_profile = profile().model_copy(update={"auto_reconnect_adb_enabled": False})
    runner = FakeRunner([])
    disabled_runtime = AdbRuntime(
        disabled_profile,
        "/opt/homebrew/bin/adb",
        runner,
        lambda: "123456",
    )

    # When
    envelope, exit_code = execute(
        ("wireless-prepare", "--approved"),
        disabled_runtime,
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "auto_reconnect_disabled"
    assert runner.calls == []


def test_wireless_prepare_reuses_verified_enrolled_transport_without_connecting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            *identity_results(),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["ready"] is True
    assert envelope["result"]["reused"] is True
    assert envelope["result"]["endpoint"] == "DEMO123456"
    assert all("mdns" not in call[0] and "connect" not in call[0] for call in runner.calls)


def test_wireless_prepare_labels_native_mdns_transport_as_tcpip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    native_serial = "adb-DEMO123456-live._adb-tls-connect._tcp"
    runner = FakeRunner(
        [
            result(
                f"List of devices attached\n{native_serial} device model:SM_S921B transport_id:1\n"
            ),
            *identity_results(),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["endpoint"] == native_serial
    assert envelope["result"]["route"]["transport"] == "adb_tcpip"


def test_wireless_prepare_discovers_connects_and_verifies_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-DEMO123456-live _adb-tls-connect._tcp. 192.168.1.20:32002\n"
            ),
            result("connected to 100.64.1.20:32002\n"),
            *identity_results(),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["ready"] is True
    assert envelope["result"]["reused"] is False
    assert envelope["result"]["discovery"] == "adb_mdns"
    assert envelope["result"]["endpoint"] == "100.64.1.20:32002"
    connect_calls = [call for call in runner.calls if "connect" in call[0]]
    assert connect_calls == [(("/opt/homebrew/bin/adb", "connect", "100.64.1.20:32002"), None)]


def test_wireless_prepare_requires_displayed_port_when_mdns_has_no_match() -> None:
    # Given
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-OTHER-live _adb-tls-connect._tcp. 192.168.1.30:32002\n"
            ),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "connection_port_required"
    assert all("connect" not in call[0] for call in runner.calls)


def test_wireless_prepare_requires_displayed_port_when_mdns_command_fails() -> None:
    # Given
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(stderr="mDNS unavailable", returncode=1),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "connection_port_required"
    assert all("connect" not in call[0] for call in runner.calls)


def test_wireless_prepare_refuses_ambiguous_enrolled_ports() -> None:
    # Given
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-DEMO123456-a _adb-tls-connect._tcp. 192.168.1.20:32002\n"
                "adb-DEMO123456-b _adb-tls-connect._tcp. 192.168.1.20:32003\n"
            ),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "mdns_ambiguous"
    assert all("connect" not in call[0] for call in runner.calls)


def test_wireless_prepare_does_not_pair_after_connect_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-DEMO123456-live _adb-tls-connect._tcp. 192.168.1.20:32002\n"
            ),
            result(stderr="failed to authenticate", returncode=1),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "adb_connect_failed"
    assert len([call for call in runner.calls if "connect" in call[0]]) == 1
    assert all("pair" not in call[0] for call in runner.calls)


def test_wireless_prepare_rejects_zero_exit_connect_failure_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-DEMO123456-live _adb-tls-connect._tcp. 192.168.1.20:32002\n"
            ),
            result("failed to connect to 100.64.1.20:32002\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "adb_connect_failed"
    assert len(runner.calls) == 3


def test_wireless_prepare_disconnects_endpoint_after_identity_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("List of devices attached\n"),
            result(
                "List of discovered mdns services\n"
                "adb-DEMO123456-live _adb-tls-connect._tcp. 192.168.1.20:32002\n"
            ),
            result("connected to 100.64.1.20:32002\n"),
            result("device\n"),
            result("OTHER123456\n"),
            result("SM-S921B\n"),
            result("disconnected 100.64.1.20:32002\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "device_mismatch"
    assert runner.calls[-1] == (
        ("/opt/homebrew/bin/adb", "disconnect", "100.64.1.20:32002"),
        None,
    )


def test_wireless_prepare_never_reuses_fixed_tcp_5555_transport() -> None:
    # Given
    runner = FakeRunner(
        [
            result(
                "List of devices attached\n100.64.1.20:5555 device model:SM_S921B transport_id:1\n"
            ),
            result("List of discovered mdns services\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-prepare", "--approved"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "connection_port_required"
    assert runner.calls == [
        (("/opt/homebrew/bin/adb", "devices", "-l"), None),
        (("/opt/homebrew/bin/adb", "mdns", "services"), None),
    ]


def test_wireless_connect_rejects_non_uuid_boot_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    invalid_boot = "z" * 36
    runner = FakeRunner(
        [
            result("connected\n"),
            result("device\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(f"{invalid_boot}\n"),
            result("disconnected 100.64.1.20:32002\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-connect", "--port", "32002"), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "boot_session_unavailable"


def test_wireless_connect_hashes_canonical_boot_uuid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "state"))
    runner = FakeRunner(
        [
            result("connected\n"),
            result("device\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(f"{BOOT_ID.upper()}\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-connect", "--port", "32002"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["boot_session_hash"] == hashlib.sha256(BOOT_ID.encode()).hexdigest()


def test_wireless_status_labels_usb_only_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_WIRELESS_STATE_DIR", str(tmp_path / "wireless"))
    runner = FakeRunner(
        [result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n")]
    )

    # When
    envelope, exit_code = execute(("wireless-status",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["route"]["transport"] == "adb_usb"


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
            result("disconnected 100.64.1.20:32002\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("wireless-recover", "--port", "32002"), runtime(recover_runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "boot_session_mismatch"
