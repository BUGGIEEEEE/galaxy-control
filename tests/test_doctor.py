from __future__ import annotations

from collections.abc import Callable

from galaxy_doctor_core import DoctorRuntime, inspect_device
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from openminis_client import ClientError, SuccessResponse
from openminis_protocol import Action, BridgeRequest


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        self.calls.append(argv)
        assert stdin is None
        return self.responses.pop(0)


def result(stdout: str, returncode: int = 0) -> CommandResult:
    return CommandResult(returncode=returncode, stdout=stdout, stderr="")


def profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        steady_adb_enabled=False,
    )


def bridge(request: BridgeRequest) -> SuccessResponse:
    payloads = {
        Action.HEALTH: {"status": "ok"},
        Action.A11Y_STATUS: {"running": True, "capabilities": ["performGestures"]},
        Action.SHIZUKU_STATUS: {"state": "READY", "running": True, "authorized": True},
    }
    return SuccessResponse(ok=True, action=request.action, result=payloads[request.action])


def paths(name: str) -> str | None:
    return {
        "adb": "/opt/homebrew/bin/adb",
        "scrcpy": "/opt/homebrew/bin/scrcpy",
        "tailscale": "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    }.get(name)


def test_doctor_combines_openminis_adb_scrcpy_and_tailscale() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\nVersion 36.0.0\n"),
            result("List of devices attached\nDEMO123456 device model:SM-S921B usb:1-1\n"),
            result("scrcpy 3.3.3\n"),
            result('{"BackendState":"Running","Self":{"Online":true}}\n'),
        ]
    )
    runtime = DoctorRuntime(profile(), runner, paths, bridge)

    # When
    report = inspect_device(runtime)

    # Then
    assert report["status"] == "READY"
    assert report["openminis"]["health"]["available"] is True
    assert report["openminis"]["accessibility"]["available"] is True
    assert report["adb"]["identity_match"] is True
    assert report["adb"]["devices"][0]["transport"] == "usb"
    assert report["scrcpy"]["installed"] is True
    assert report["tailscale"]["online"] is True
    assert report["control_paths"] == {
        "openminis": True,
        "scrcpy": True,
        "adb": True,
        "shizuku": True,
    }
    assert all("connect" not in call and "tcpip" not in call for call in runner.calls)


def test_doctor_returns_partial_results_when_every_path_fails() -> None:
    # Given
    def missing(_name: str) -> None:
        return None

    def failed_bridge(request: BridgeRequest) -> SuccessResponse:
        raise ClientError("network_error", f"{request.action.value} unavailable")

    runtime = DoctorRuntime(profile(), FakeRunner([]), missing, failed_bridge)

    # When
    report = inspect_device(runtime)

    # Then
    assert report["status"] == "BLOCKED"
    assert report["openminis"]["health"] == {
        "available": False,
        "error": "network_error",
    }
    assert report["adb"] == {"installed": False, "devices": [], "error": "adb_not_installed"}
    assert report["scrcpy"] == {"installed": False}
    assert report["tailscale"] == {"installed": False, "online": False}
    assert report["control_paths"] == {
        "openminis": False,
        "scrcpy": False,
        "adb": False,
        "shizuku": False,
    }


def test_doctor_marks_live_different_model_as_mismatch() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\nDEMO123456 device model:SM-G991B usb:1-1\n"),
            result("scrcpy 3.3.3\n"),
            result('{"BackendState":"Running","Self":{"Online":true}}\n'),
        ]
    )

    # When
    report = inspect_device(DoctorRuntime(profile(), runner, paths, bridge))

    # Then
    assert report["status"] == "DEGRADED"
    assert report["adb"]["identity_match"] is False
    assert report["adb"]["error"] == "device_mismatch"
    assert report["control_paths"]["adb"] is False
    assert report["control_paths"]["scrcpy"] is False


def test_doctor_bridge_callable_has_typed_contract() -> None:
    # Given / When
    callback: Callable[[BridgeRequest], SuccessResponse] = bridge

    # Then
    assert callback(BridgeRequest(Action.HEALTH)).action is Action.HEALTH
