#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Enroll one Galaxy with galaxy_setup.py.
# 2. Diagnose: uv run galaxy_bridge_package.py doctor
# 3. Build once: uv run galaxy_bridge_package.py build --output /ABSOLUTE/NEW/DIR --approved
# ──────────────────

"""Build a private per-user OpenMinis Control v2 bridge handoff."""

from __future__ import annotations

import ipaddress
import json
import os
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from galaxy_bridge_builder import BridgeIdentity, BridgePackageError, build_bridge_package
from galaxy_process import JsonObject, Runner, error_envelope, run_command, success_envelope
from galaxy_profile import DeviceProfile, ProfileError, load_profile
from galaxy_setup import find_executable

TAILNET: Final = ipaddress.IPv4Network("100.64.0.0/10")
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
DEFAULT_ASSET_ROOT: Final = Path(__file__).parent.parent / "assets" / "openminis-control-v2"


@dataclass(frozen=True, slots=True)
class BridgePackageRuntime:
    """Injectable boundaries for bridge package diagnosis and generation."""

    runner: Runner
    which: Callable[[str], str | None]
    profile_loader: Callable[[], DeviceProfile]
    asset_root: Path


def _mac_tailnet_ipv4(runtime: BridgePackageRuntime, phone_ipv4: str) -> str:
    tailscale = runtime.which("tailscale")
    if tailscale is None:
        raise BridgePackageError("tailscale_not_installed", "Tailscale CLI is unavailable")
    result = runtime.runner((tailscale, "ip", "-4"))
    if not result.succeeded:
        raise BridgePackageError("tailscale_unavailable", "Tailscale IPv4 cannot be read")
    candidates: list[str] = []
    for raw in result.stdout.splitlines():
        try:
            address = ipaddress.IPv4Address(raw)
        except ipaddress.AddressValueError:
            continue
        if address in TAILNET:
            candidates.append(str(address))
    if len(candidates) != 1 or candidates[0] == phone_ipv4:
        raise BridgePackageError(
            "mac_tailnet_identity_invalid",
            "exactly one distinct Mac Tailscale IPv4 is required",
        )
    return candidates[0]


def _identity(runtime: BridgePackageRuntime) -> BridgeIdentity:
    profile = runtime.profile_loader()
    mac_ipv4 = _mac_tailnet_ipv4(runtime, profile.tailscale_ipv4)
    try:
        return BridgeIdentity(
            phone_ipv4=profile.tailscale_ipv4,
            trusted_mac_ipv4=mac_ipv4,
            port=profile.openminis_port,
        )
    except ValidationError as error:
        raise BridgePackageError(
            "bridge_identity_invalid", "enrolled bridge identity is invalid"
        ) from error


def _validate_output(path: Path) -> None:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise BridgePackageError("output_path_invalid", "output must be an absolute new directory")
    if path.exists() or path.is_symlink():
        raise BridgePackageError("output_target_exists", "output target already exists")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise BridgePackageError("output_parent_invalid", "output parent must be a real directory")


def _private_write(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
    except OSError as error:
        raise BridgePackageError(
            "package_write_failed", "package file cannot be created"
        ) from error
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            _ = stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
        ):
            raise BridgePackageError("package_write_failed", "package file identity is unsafe")
    except OSError as error:
        raise BridgePackageError(
            "package_write_failed", "package file cannot be finalized"
        ) from error


def _write_package(output: Path, runtime: BridgePackageRuntime) -> JsonObject:
    _validate_output(output)
    package = build_bridge_package(_identity(runtime), runtime.asset_root)
    try:
        output.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        output.chmod(PRIVATE_DIRECTORY_MODE)
    except OSError as error:
        raise BridgePackageError(
            "package_write_failed", "package directory cannot be created"
        ) from error
    _private_write(output / package.artifact_name, package.artifact)
    _private_write(output / "INSTALL.md", package.install_instruction.encode())
    _private_write(output / "LIFECYCLE.md", package.lifecycle_instruction.encode())
    checksums = (
        f"{package.artifact_sha256}  {package.artifact_name}\n"
        f"{package.manifest_sha256}  RUNTIME_MANIFEST\n"
    )
    _private_write(output / "SHA256SUMS", checksums.encode())
    return {
        "status": "PACKAGE_READY",
        "artifact_name": package.artifact_name,
        "artifact_sha256": package.artifact_sha256,
        "output_directory": str(output),
        "contains_private_network_identity": True,
        "share_only_with_target_minis": True,
    }


def execute(argv: Sequence[str], runtime: BridgePackageRuntime) -> tuple[JsonObject, int]:
    """Execute one strict bridge package command."""
    action = argv[0] if argv else "unknown"
    try:
        match tuple(argv):  # noqa: V001  # noqa: MATCH_OK -- reject every unknown form.
            case ("doctor",):
                identity = _identity(runtime)
                _ = build_bridge_package(identity, runtime.asset_root)
                result: JsonObject = {
                    "status": "READY",
                    "profile_enrolled": True,
                    "phone_tailnet_identity_valid": True,
                    "mac_tailnet_identity_valid": True,
                    "bridge_assets_valid": True,
                    "network_values_disclosed": False,
                }
            case ("build", "--output", _):
                raise BridgePackageError(
                    "approval_required", "building a personalized handoff requires approval"
                )
            case ("build", "--output", raw_output, "--approved"):
                result = _write_package(Path(raw_output), runtime)
            case _:
                raise BridgePackageError("invalid_request", "unsupported bridge package command")
    except (BridgePackageError, ProfileError) as error:
        return error_envelope(action, error.code, error.message), 1
    return success_envelope(action, result), 0


def main(argv: Sequence[str] | None = None) -> int:
    """Print exactly one JSON envelope."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    runtime = BridgePackageRuntime(run_command, find_executable, load_profile, DEFAULT_ASSET_ROOT)
    envelope, exit_code = execute(args, runtime)
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
