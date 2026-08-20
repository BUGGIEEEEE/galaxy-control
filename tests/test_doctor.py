from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from galaxy_doctor import execute, main
from galaxy_doctor_core import DoctorRuntime, PreflightTarget, inspect_device
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile
from openminis_client import ClientError, SuccessResponse
from openminis_protocol import Action, BridgeRequest

if TYPE_CHECKING:
    import pytest


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
        Action.A11Y_STATUS: {
            "ok": True,
            "data": {"running": True, "capabilities": ["performGestures"]},
            "route": {"controller": "openminis"},
        },
        Action.SHIZUKU_STATUS: {
            "ok": True,
            "data": {
                "state": "READY",
                "running": True,
                "authorized": True,
            },
            "route": {"controller": "openminis"},
        },
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


def test_doctor_requires_running_accessibility_service() -> None:
    # Given
    def stopped_accessibility(request: BridgeRequest) -> SuccessResponse:
        response = bridge(request)
        if request.action is not Action.A11Y_STATUS:
            return response
        return SuccessResponse(
            ok=True,
            action=request.action,
            result={
                "ok": True,
                "data": {"running": False, "capabilities": []},
                "route": {"controller": "openminis"},
            },
        )

    runtime = DoctorRuntime(profile(), FakeRunner([]), paths, stopped_accessibility)

    # When
    report = inspect_device(runtime, target=PreflightTarget.OPENMINIS)

    # Then
    assert report["status"] == "BLOCKED"
    assert report["control_paths"] == {"openminis": False}


def test_doctor_bridge_callable_has_typed_contract() -> None:
    # Given / When
    callback: Callable[[BridgeRequest], SuccessResponse] = bridge

    # Then
    assert callback(BridgeRequest(Action.HEALTH)).action is Action.HEALTH


def test_openminis_preflight_skips_adb_scrcpy_and_shizuku() -> None:
    # Given
    runner = FakeRunner([])
    checked: list[Action] = []

    def tracked_bridge(request: BridgeRequest) -> SuccessResponse:
        checked.append(request.action)
        return bridge(request)

    runtime = DoctorRuntime(profile(), runner, paths, tracked_bridge)

    # When
    report = inspect_device(runtime, target=PreflightTarget.OPENMINIS)

    # Then
    assert runner.calls == []
    assert checked == [Action.HEALTH, Action.A11Y_STATUS]
    assert report["requested_path"] == "openminis"
    assert report["checked_paths"] == ["openminis"]
    assert report["control_paths"] == {"openminis": True}


def test_adb_preflight_skips_openminis_scrcpy_and_tailscale() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\nDEMO123456 device model:SM-S921B usb:1-1\n"),
        ]
    )

    def unexpected_bridge(_request: BridgeRequest) -> SuccessResponse:
        raise AssertionError("OpenMinis must not run for an ADB-only preflight")

    runtime = DoctorRuntime(profile(), runner, paths, unexpected_bridge)

    # When
    report = inspect_device(runtime, target=PreflightTarget.ADB)

    # Then
    assert len(runner.calls) == 2
    assert all("scrcpy" not in call and "tailscale" not in call for call in runner.calls)
    assert report["requested_path"] == "adb"
    assert report["checked_paths"] == ["adb"]
    assert report["control_paths"] == {"adb": True}


def test_scrcpy_preflight_requires_adb_without_openminis_or_tailscale() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\nDEMO123456 device model:SM-S921B usb:1-1\n"),
            result("scrcpy 3.3.3\n"),
        ]
    )

    def unexpected_bridge(_request: BridgeRequest) -> SuccessResponse:
        raise AssertionError("OpenMinis must not run for a scrcpy preflight")

    runtime = DoctorRuntime(profile(), runner, paths, unexpected_bridge)

    # When
    report = inspect_device(runtime, target=PreflightTarget.SCRCPY)

    # Then
    assert len(runner.calls) == 3
    assert all("tailscale" not in call for call in runner.calls)
    assert report["requested_path"] == "scrcpy"
    assert report["checked_paths"] == ["adb", "scrcpy"]
    assert report["control_paths"] == {"adb": True, "scrcpy": True}


def test_scrcpy_preflight_is_blocked_when_scrcpy_is_unavailable() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\nDEMO123456 device model:SM-S921B usb:1-1\n"),
        ]
    )
    runtime = DoctorRuntime(
        profile(),
        runner,
        lambda name: paths(name) if name != "scrcpy" else None,
        bridge,
    )

    # When
    report = inspect_device(runtime, target=PreflightTarget.SCRCPY)

    # Then
    assert report["status"] == "BLOCKED"
    assert report["control_paths"] == {"adb": True, "scrcpy": False}


def test_adb_preflight_verifies_physical_serial_behind_remote_transport() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\n100.64.1.20:32002 device model:SM_S921B\n"),
            result("DEMO123456\n"),
        ]
    )
    runtime = DoctorRuntime(profile(), runner, paths, bridge)

    # When
    report = inspect_device(runtime, target=PreflightTarget.ADB)

    # Then
    assert report["control_paths"] == {"adb": True}
    assert runner.calls[-1] == (
        "/opt/homebrew/bin/adb",
        "-s",
        "100.64.1.20:32002",
        "shell",
        "getprop",
        "ro.serialno",
    )


def test_adb_preflight_rejects_disabled_fixed_tcp_transport() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\n100.64.1.20:5555 device model:SM_S921B\n"),
        ]
    )

    # When
    report = inspect_device(
        DoctorRuntime(profile(), runner, paths, bridge),
        target=PreflightTarget.ADB,
    )

    # Then
    assert report["status"] == "BLOCKED"
    assert report["control_paths"] == {"adb": False}
    assert len(runner.calls) == 2


def test_adb_preflight_accepts_verified_native_mdns_alias() -> None:
    # Given
    native_serial = "adb-DEMO123456-live._adb-tls-connect._tcp"
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result(
                f"List of devices attached\n{native_serial} device model:SM_S921B transport_id:1\n"
            ),
            result("DEMO123456\n"),
        ]
    )

    # When
    report = inspect_device(
        DoctorRuntime(profile(), runner, paths, bridge),
        target=PreflightTarget.ADB,
    )

    # Then
    assert report["status"] == "READY"
    assert report["control_paths"] == {"adb": True}
    assert report["adb"]["devices"][0]["transport"] == "tcpip"


def test_adb_preflight_rejects_dynamic_transport_for_steady_profile() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\n100.64.1.20:32002 device model:SM_S921B\n"),
        ]
    )
    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})

    # When
    report = inspect_device(
        DoctorRuntime(steady_profile, runner, paths, bridge),
        target=PreflightTarget.ADB,
    )

    # Then
    assert report["status"] == "BLOCKED"
    assert report["control_paths"] == {"adb": False}
    assert report["adb"]["error"] == "device_mismatch"


def test_adb_preflight_rejects_usb_transport_for_steady_profile() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
        ]
    )
    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})

    # When
    report = inspect_device(
        DoctorRuntime(steady_profile, runner, paths, bridge),
        target=PreflightTarget.ADB,
    )

    # Then
    assert report["status"] == "BLOCKED"
    assert report["control_paths"] == {"adb": False}
    assert report["adb"]["error"] == "device_mismatch"


def test_adb_preflight_accepts_fixed_transport_for_steady_profile() -> None:
    # Given
    runner = FakeRunner(
        [
            result("Android Debug Bridge version 1.0.41\n"),
            result("List of devices attached\n100.64.1.20:5555 device model:SM_S921B\n"),
            result("DEMO123456\n"),
        ]
    )
    steady_profile = profile().model_copy(update={"steady_adb_enabled": True})

    # When
    report = inspect_device(
        DoctorRuntime(steady_profile, runner, paths, bridge),
        target=PreflightTarget.ADB,
    )

    # Then
    assert report["status"] == "READY"
    assert report["control_paths"] == {"adb": True}


def test_doctor_cli_accepts_only_fixed_preflight_targets() -> None:
    # Given
    runtime = DoctorRuntime(
        profile(),
        FakeRunner(
            [
                result("Android Debug Bridge version 1.0.41\n"),
                result("List of devices attached\nDEMO123456 device model:SM-S921B usb:1-1\n"),
            ]
        ),
        paths,
        bridge,
    )

    # When
    envelope, exit_code = execute(("adb",), runtime)

    # Then
    assert exit_code == 0
    assert envelope["result"]["requested_path"] == "adb"


def test_doctor_cli_rejects_unknown_preflight_target() -> None:
    # Given / When
    envelope, exit_code = execute(
        ("shell",),
        DoctorRuntime(profile(), FakeRunner([]), paths, bridge),
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "invalid_request"


def test_doctor_main_rejects_invalid_target_before_profile_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "missing"))

    # When
    exit_code = main(("shell",))
    output = json.loads(capsys.readouterr().out)

    # Then
    assert exit_code == 1
    assert output["error"]["code"] == "invalid_request"


def test_preflight_result_declares_session_reuse_and_invalidation_contract() -> None:
    # Given
    runtime = DoctorRuntime(profile(), FakeRunner([]), paths, bridge)

    # When
    report = inspect_device(runtime, target=PreflightTarget.OPENMINIS)

    # Then
    assert report["reuse"] == {
        "scope": "current_agent_session",
        "persisted": False,
        "invalidate_on": [
            "device_reboot",
            "network_change",
            "bridge_error",
            "adb_error",
            "process_death",
        ],
    }
