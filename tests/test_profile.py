from __future__ import annotations

import json
from pathlib import Path

import pytest

from galaxy_profile import DeviceProfile, ProfileError, load_profile, profile_path, write_profile


def example_profile() -> DeviceProfile:
    return DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=False,
    )


def test_profile_round_trip_when_private_directory_is_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))

    # When
    written = write_profile(example_profile())
    loaded = load_profile()

    # Then
    assert written == profile_path()
    assert loaded == example_profile()
    assert written.stat().st_mode & 0o777 == 0o600
    assert written.parent.stat().st_mode & 0o777 == 0o700


def test_profile_rejected_when_tailscale_address_is_not_tailnet() -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="tailscale_ipv4"):
        DeviceProfile(
            schema=1,
            physical_serial="DEMO123456",
            expected_model="SM_S921B",
            tailscale_ipv4="192.0.2.10",
            openminis_port=43129,
            steady_adb_enabled=False,
        )


def test_profile_rejected_when_file_is_world_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    support = tmp_path / "support"
    support.mkdir(mode=0o700)
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(support))
    path = profile_path()
    path.write_text(json.dumps(example_profile().model_dump(mode="json")))
    path.chmod(0o644)

    # When / Then
    with pytest.raises(ProfileError, match="private"):
        load_profile()


def test_profile_rejected_when_path_is_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    support = tmp_path / "support"
    support.mkdir(mode=0o700)
    target = tmp_path / "target.json"
    target.write_text("{}")
    (support / "device.json").symlink_to(target)
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(support))

    # When / Then
    with pytest.raises(ProfileError, match="regular"):
        load_profile()


def test_profile_requires_exact_schema() -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="schema"):
        DeviceProfile.model_validate(
            {
                "schema": 2,
                "physical_serial": "DEMO123456",
                "expected_model": "SM_S921B",
                "tailscale_ipv4": "100.64.1.20",
                "openminis_port": 43129,
                "steady_adb_enabled": False,
            }
        )
