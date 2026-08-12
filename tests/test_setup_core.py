from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from galaxy_process import CommandResult
from galaxy_setup_core import SetupError, SetupRuntime, apply_plan, build_plan, enroll


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


def runtime(runner: FakeRunner, which: Callable[[str], str | None]) -> SetupRuntime:
    return SetupRuntime(runner=runner, which=which)


def test_enroll_reads_identity_and_tailnet_address_from_one_live_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(
                "7: wlan0    inet 192.168.1.20/24 scope global wlan0\n"
                "8: tun0    inet 100.64.1.20/32 scope global tun0\n"
            ),
        ]
    )
    env = runtime(runner, lambda name: "/opt/homebrew/bin/adb" if name == "adb" else None)

    # When
    profile = enroll(env)

    # Then
    assert profile.physical_serial == "DEMO123456"
    assert profile.expected_model == "SM_S921B"
    assert profile.tailscale_ipv4 == "100.64.1.20"
    assert runner.calls[-1] == (
        "/opt/homebrew/bin/adb",
        "-s",
        "DEMO123456",
        "shell",
        "ip",
        "-o",
        "-4",
        "addr",
        "show",
    )


def test_enroll_refuses_multiple_devices() -> None:
    # Given
    runner = FakeRunner(
        [
            result(
                "List of devices attached\nONE device model:SM_S921B usb:1-1\n"
                "TWO device model:SM_S921B usb:1-2\n"
            )
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError, match="multiple"):
        enroll(env)


def test_enroll_accepts_exact_live_serial_when_multiple_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    runner = FakeRunner(
        [
            result(
                "List of devices attached\nOTHER123 device model:SM_S921B usb:1-1\n"
                "DEMO123456 device model:SM_S921B usb:1-2\n"
            ),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result("8: tun0    inet 100.64.1.20/32 scope global tun0\n"),
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When
    enrolled = enroll(env, "DEMO123456")

    # Then
    assert enrolled.physical_serial == "DEMO123456"
    assert runner.calls[1][:3] == ("/opt/homebrew/bin/adb", "-s", "DEMO123456")


def test_enroll_refuses_remote_adb_transport_as_trust_root() -> None:
    # Given
    runner = FakeRunner(
        [
            result(
                "List of devices attached\n100.64.1.20:5555 device model:SM_F956N transport_id:2\n"
            ),
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env, "100.64.1.20:5555")
    assert captured.value.code == "usb_required"
    assert len(runner.calls) == 1


def test_enroll_refuses_emulator_transport_as_trust_root() -> None:
    # Given
    runner = FakeRunner(
        [result("List of devices attached\nemulator-5554 device model:SM_S921B transport_id:1\n")]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env, "emulator-5554")
    assert captured.value.code == "usb_required"
    assert len(runner.calls) == 1


def test_enroll_refuses_usb_transport_with_mismatched_physical_serial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            result("DIFFERENT123\n"),
            result("SM-S921B\n"),
            result("8: tun0    inet 100.64.1.20/32 scope global tun0\n"),
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env)
    assert captured.value.code == "device_mismatch"


def test_enroll_ignores_carrier_cgnat_and_uses_tunnel_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(
                "2: rmnet_data0    inet 100.65.20.3/30 scope global rmnet_data0\n"
                "8: tun0    inet 100.64.1.20/32 scope global tun0\n"
            ),
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When
    enrolled = enroll(env)

    # Then
    assert enrolled.tailscale_ipv4 == "100.64.1.20"


def test_enroll_refuses_multiple_tailnet_tunnel_candidates() -> None:
    # Given
    runner = FakeRunner(
        [
            result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n"),
            result("DEMO123456\n"),
            result("SM-S921B\n"),
            result(
                "8: tun0    inet 100.65.20.3/32 scope global tun0\n"
                "9: tun1    inet 100.64.1.20/32 scope global tun1\n"
            ),
        ]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env)
    assert captured.value.code == "tailscale_address_ambiguous"


def test_enroll_rejects_serial_not_in_live_list_without_using_it() -> None:
    # Given
    runner = FakeRunner(
        [result("List of devices attached\nDEMO123456 device model:SM_S921B usb:1-1\n")]
    )
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env, "--shell-injection")
    assert captured.value.code == "device_not_listed"
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    ("state", "code"),
    [("unauthorized", "adb_unauthorized"), ("offline", "adb_offline")],
)
def test_enroll_refuses_unavailable_device(state: str, code: str) -> None:
    # Given
    runner = FakeRunner([result(f"List of devices attached\nDEMO123456 {state}\n")])
    env = runtime(runner, lambda _: "/opt/homebrew/bin/adb")

    # When / Then
    with pytest.raises(SetupError) as captured:
        enroll(env)
    assert captured.value.code == code


def test_plan_contains_only_missing_reviewed_tools() -> None:
    # Given
    available = {"brew": "/opt/homebrew/bin/brew", "adb": "/opt/homebrew/bin/adb"}
    env = runtime(FakeRunner([]), available.get)

    # When
    plan = build_plan(env)

    # Then
    assert plan.install_commands == (
        ("/opt/homebrew/bin/brew", "install", "scrcpy"),
        ("/opt/homebrew/bin/brew", "install", "uv"),
    )
    assert plan.user_actions == ("install_or_open_tailscale_standalone",)


def test_plan_does_not_update_present_tools() -> None:
    # Given
    paths = {
        "brew": "/opt/homebrew/bin/brew",
        "adb": "/opt/homebrew/bin/adb",
        "scrcpy": "/opt/homebrew/bin/scrcpy",
        "uv": "/opt/homebrew/bin/uv",
        "tailscale": "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    }
    env = runtime(FakeRunner([]), paths.get)

    # When
    plan = build_plan(env)

    # Then
    assert plan.install_commands == ()
    assert plan.user_actions == ()


def test_apply_runs_only_the_reviewed_missing_tool_commands() -> None:
    # Given
    runner = FakeRunner([result("installed\n"), result("installed\n")])
    available = {"brew": "/opt/homebrew/bin/brew", "adb": "/opt/homebrew/bin/adb"}
    env = runtime(runner, available.get)
    plan = build_plan(env)

    # When
    applied = apply_plan(plan, env)

    # Then
    assert applied == 2
    assert runner.calls == [
        ("/opt/homebrew/bin/brew", "install", "scrcpy"),
        ("/opt/homebrew/bin/brew", "install", "uv"),
    ]


def test_apply_stops_on_failed_reviewed_installer() -> None:
    # Given
    runner = FakeRunner([result("", returncode=1)])
    available = {"brew": "/opt/homebrew/bin/brew", "adb": "/opt/homebrew/bin/adb"}
    env = runtime(runner, available.get)

    # When / Then
    with pytest.raises(SetupError) as captured:
        apply_plan(build_plan(env), env)
    assert captured.value.code == "prerequisite_install_failed"
