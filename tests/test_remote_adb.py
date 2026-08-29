from __future__ import annotations

from collections.abc import Callable

import pytest

from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from galaxy_remote_adb import AdbRuntime, execute


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        self.calls.append((argv, stdin))
        return self.responses.pop(0)


def result(stdout: str = "", returncode: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(returncode, stdout, stderr)


def profile(*, steady: bool = True) -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=steady,
    )


def runtime(
    runner: FakeRunner,
    *,
    steady: bool = True,
    pair_code_reader: Callable[[], str] = lambda: "123456",
) -> AdbRuntime:
    return AdbRuntime(profile(steady=steady), "/opt/homebrew/bin/adb", runner, pair_code_reader)


def test_legacy_connect_uses_profile_endpoint_and_verifies_identity() -> None:
    # Given
    runner = FakeRunner(
        [
            result("connected\n"),
            result("device\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result("11111111-2222-3333-4444-555555555555\n"),
        ]
    )

    # When
    envelope, exit_code = execute(("legacy-connect",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["endpoint"] == "100.64.1.20:5555"
    assert envelope["result"]["boot_session_hash"]
    assert runner.calls[0][0] == ("/opt/homebrew/bin/adb", "connect", "100.64.1.20:5555")
    assert envelope["result"]["route"] == {
        "controller": "adb",
        "transport": "adb_tcpip",
        "role": "connect",
        "verification_required": False,
        "verify_with": [],
    }


def test_connect_rejected_when_steady_path_is_not_enabled() -> None:
    # Given / When
    envelope, exit_code = execute(("legacy-connect",), runtime(FakeRunner([]), steady=False))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "steady_adb_disabled"


def test_status_labels_connected_remote_transport() -> None:
    # Given
    runner = FakeRunner(
        [
            result(
                "List of devices attached\n100.64.1.20:5555 device model:SM_S921B transport_id:2\n"
            )
        ]
    )

    # When
    envelope, exit_code = execute(("status",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["route"]["transport"] == "adb_tcpip"


def test_status_does_not_label_offline_steady_endpoint_connected() -> None:
    # Given
    runner = FakeRunner(
        [
            result(
                "List of devices attached\n100.64.1.20:5555 offline model:SM_S921B transport_id:2\n"
            )
        ]
    )

    # When
    envelope, exit_code = execute(("status",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["remote_connected"] is False
    assert envelope["result"]["devices"][0]["state"] == "offline"


def test_disconnect_labels_remote_transport_and_requires_verification() -> None:
    # Given
    runner = FakeRunner([result("disconnected\n")])

    # When
    envelope, exit_code = execute(("disconnect",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["route"]["transport"] == "adb_tcpip"
    assert envelope["result"]["route"]["verification_required"] is True


def test_restore_usb_requires_post_action_verification() -> None:
    # Given
    runner = FakeRunner([result("restarting in USB mode\n")])

    # When
    envelope, exit_code = execute(("restore-usb", "--approved"), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["route"]["transport"] == "adb_tcpip"
    assert envelope["result"]["route"]["verification_required"] is True


@pytest.mark.parametrize(
    ("state_output", "code"),
    [
        ("unauthorized\n", "adb_unauthorized"),
        ("offline\n", "adb_offline"),
        ("unknown\n", "adb_no_device"),
    ],
)
def test_connect_classifies_unavailable_state(state_output: str, code: str) -> None:
    # Given
    runner = FakeRunner([result("connected\n"), result(state_output, returncode=1)])

    # When
    envelope, exit_code = execute(("legacy-connect",), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == code


def test_connect_rejects_identity_mismatch() -> None:
    # Given
    runner = FakeRunner(
        [result("connected\n"), result("device\n"), result("DEMO123456\n"), result("SM-OTHER\n")]
    )

    # When
    envelope, exit_code = execute(("legacy-connect",), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "device_mismatch"


def test_usb_enable_requires_approval_before_any_call() -> None:
    # Given
    runner = FakeRunner([])

    # When
    envelope, exit_code = execute(("enable",), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "approval_required"
    assert runner.calls == []


def test_usb_enable_uses_only_enrolled_serial_and_fixed_port() -> None:
    # Given
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            result("restarting in TCP mode port: 5555\n"),
        ]
    )

    # When
    _envelope, exit_code = execute(("enable", "--approved"), runtime(runner))

    # Then
    assert exit_code == 0
    assert runner.calls[-1][0] == (
        "/opt/homebrew/bin/adb",
        "-s",
        "DEMO123456",
        "tcpip",
        "5555",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ("legacy-connect", "--host", "example.invalid"),
        ("legacy-connect", "--serial", "DEMO123456"),
        ("legacy-connect", "--port", "5555"),
        ("connect", "--tcpip", "5555"),
        ("shell", "id"),
    ],
)
def test_arbitrary_remote_adb_inputs_are_rejected(argv: tuple[str, ...]) -> None:
    # Given / When
    envelope, exit_code = execute(argv, runtime(FakeRunner([])))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "invalid_request"
