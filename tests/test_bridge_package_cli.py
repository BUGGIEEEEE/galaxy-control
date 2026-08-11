from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_bridge_package import BridgePackageRuntime, execute
from galaxy_process import CommandResult
from galaxy_profile import DeviceProfile

ROOT = Path(__file__).parent.parent
ASSET_ROOT = ROOT / "skill" / "galaxy-control" / "assets" / "openminis-control-v2"


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
        self.calls.append(argv)
        assert stdin is None
        return self.responses.pop(0)


def example_profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=False,
    )


def runtime(runner: FakeRunner) -> BridgePackageRuntime:
    return BridgePackageRuntime(
        runner=runner,
        which=lambda name: (
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale" if name == "tailscale" else None
        ),
        profile_loader=example_profile,
        asset_root=ASSET_ROOT,
    )


def test_doctor_reads_exact_local_tailscale_identity_without_disclosing_addresses() -> None:
    # Given
    runner = FakeRunner([CommandResult(0, "100.64.1.30\n", "")])

    # When
    envelope, exit_code = execute(("doctor",), runtime(runner))

    # Then
    assert exit_code == 0
    assert envelope["result"]["status"] == "READY"
    assert runner.calls == [("/Applications/Tailscale.app/Contents/MacOS/Tailscale", "ip", "-4")]
    assert "100.64.1.20" not in str(envelope)
    assert "100.64.1.30" not in str(envelope)


def test_build_requires_explicit_approval_before_any_external_command(tmp_path: Path) -> None:
    # Given
    runner = FakeRunner([])

    # When
    envelope, exit_code = execute(("build", "--output", str(tmp_path / "bundle")), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "approval_required"
    assert runner.calls == []


def test_build_writes_private_content_addressed_handoff_bundle(tmp_path: Path) -> None:
    # Given
    runner = FakeRunner([CommandResult(0, "100.64.1.30\n", "")])
    output = tmp_path / "bridge-handoff"

    # When
    envelope, exit_code = execute(
        ("build", "--output", str(output), "--approved"),
        runtime(runner),
    )

    # Then
    result = envelope["result"]
    artifact_name = result["artifact_name"]
    assert exit_code == 0
    assert result["status"] == "PACKAGE_READY"
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / artifact_name).stat().st_mode & 0o777 == 0o600
    assert (output / "INSTALL.md").is_file()
    assert (output / "LIFECYCLE.md").is_file()
    assert (output / "SHA256SUMS").is_file()
    assert result["artifact_sha256"] in (output / "SHA256SUMS").read_text()
    assert "100.64.1.20" not in str(envelope)
    assert "100.64.1.30" not in str(envelope)


@pytest.mark.parametrize(
    "stdout",
    ["", "192.0.2.3\n", "100.64.1.30\n100.64.1.31\n", "100.64.1.20\n"],
)
def test_doctor_rejects_missing_invalid_multiple_or_phone_identity(stdout: str) -> None:
    # Given
    runner = FakeRunner([CommandResult(0, stdout, "")])

    # When
    envelope, exit_code = execute(("doctor",), runtime(runner))

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "mac_tailnet_identity_invalid"


def test_build_rejects_relative_or_existing_output_without_writing(tmp_path: Path) -> None:
    # Given
    existing = tmp_path / "existing"
    existing.mkdir()

    # When
    relative, relative_code = execute(
        ("build", "--output", "relative", "--approved"), runtime(FakeRunner([]))
    )
    present, present_code = execute(
        ("build", "--output", str(existing), "--approved"), runtime(FakeRunner([]))
    )

    # Then
    assert relative_code == 1
    assert relative["error"]["code"] == "output_path_invalid"
    assert present_code == 1
    assert present["error"]["code"] == "output_target_exists"


def test_arbitrary_identity_and_options_are_rejected_without_external_command() -> None:
    # Given
    runner = FakeRunner([])

    # When
    envelope, exit_code = execute(
        ("build", "--phone-ip", "100.64.1.99", "--approved"), runtime(runner)
    )

    # Then
    assert exit_code == 1
    assert envelope["error"]["code"] == "invalid_request"
    assert runner.calls == []
