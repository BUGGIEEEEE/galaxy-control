from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from galaxy_bridge_builder import BridgeIdentity, build_bridge_package

ROOT = Path(__file__).parent.parent
ASSET_ROOT = ROOT / "skill" / "galaxy-control" / "assets" / "openminis-control-v2"


def example_identity() -> BridgeIdentity:
    return BridgeIdentity(
        phone_ipv4="100.64.1.20",
        trusted_mac_ipv4="100.64.1.30",
        port=43129,
    )


def test_identity_accepts_two_distinct_tailnet_addresses() -> None:
    # Given / When
    identity = example_identity()

    # Then
    assert identity.phone_ipv4 == "100.64.1.20"
    assert identity.trusted_mac_ipv4 == "100.64.1.30"


@pytest.mark.parametrize(
    ("phone", "mac"),
    [
        ("192.0.2.20", "100.64.1.30"),
        ("100.64.1.20", "127.0.0.1"),
        ("100.64.1.20;touch /tmp/x", "100.64.1.30"),
        ("100.64.1.20", "100.64.1.20"),
    ],
)
def test_identity_rejects_non_tailnet_injection_or_same_peer(phone: str, mac: str) -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match="tailnet"):
        BridgeIdentity(phone_ipv4=phone, trusted_mac_ipv4=mac, port=43129)


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_identity_rejects_invalid_bridge_port(port: int) -> None:
    # Given / When / Then
    with pytest.raises(ValueError, match=r"greater than or equal|less than or equal"):
        BridgeIdentity(
            phone_ipv4="100.64.1.20",
            trusted_mac_ipv4="100.64.1.30",
            port=port,
        )


def test_package_is_deterministic_and_content_addressed() -> None:
    # Given
    identity = example_identity()

    # When
    first = build_bridge_package(identity, ASSET_ROOT)
    second = build_bridge_package(identity, ASSET_ROOT)

    # Then
    assert first == second
    assert first.artifact_name == f"openminis-control-v2-{first.artifact_sha256}.py"
    assert hashlib.sha256(first.artifact).hexdigest() == first.artifact_sha256
    compile(first.artifact, first.artifact_name, "exec")


def test_package_instruction_exposes_checksum_but_not_private_identity() -> None:
    # Given / When
    package = build_bridge_package(example_identity(), ASSET_ROOT)

    # Then
    assert package.artifact_name in package.install_instruction
    assert package.artifact_sha256 in package.install_instruction
    assert "100.64.1.20" not in package.install_instruction
    assert "100.64.1.30" not in package.install_instruction
    assert "token" not in package.install_instruction.lower()


def test_package_contains_fixed_lifecycle_commands_without_general_shell() -> None:
    # Given / When
    package = build_bridge_package(example_identity(), ASSET_ROOT)

    # Then
    assert "openminis_bridge_control.py status" in package.lifecycle_instruction
    assert "openminis_bridge_control.py start" in package.lifecycle_instruction
    assert "openminis_bridge_control.py stop" in package.lifecycle_instruction
    assert "<COMMAND>" not in package.lifecycle_instruction
    assert "eval" not in package.lifecycle_instruction


def test_public_bridge_assets_have_no_fixed_peer_address() -> None:
    # Given
    sources = tuple(ASSET_ROOT.rglob("*.py"))

    # When
    combined = "\n".join(path.read_text() for path in sources)

    # Then
    assert sources
    ipv4_literals = set(re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", combined))
    assert ipv4_literals <= {"100.64.0.0"}
    assert "OPENMINIS_BRIDGE_TOKEN=" not in combined
