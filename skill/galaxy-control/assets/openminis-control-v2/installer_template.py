#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Do not run this template from the public skill directory.
# 2. Generate a personalized, content-addressed copy with galaxy_bridge_package.py.
# 3. Attach only that generated copy to Minis and use its generated INSTALL.md once.
# ──────────────────

"""Generated one-shot installer template for OpenMinis Control v2."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import ipaddress
import json
import os
import secrets
import stat
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

VERSION: Final = "0.3.1"
PHONE_IPV4: Final = "__PHONE_IPV4__"
TRUSTED_MAC_IPV4: Final = "__TRUSTED_MAC_IPV4__"
PORT: Final = int("__PORT__")
APPROVAL_BINDING: Final = "__APPROVAL_BINDING__"
MANIFEST_SHA256: Final = "__MANIFEST_SHA256__"
MANIFEST_JSON: Final = r"""__MANIFEST_JSON__"""
ARCHIVE_B64: Final = "__ARCHIVE_B64__"
INSTALL_ROOT: Final = ".local/share/openminis-bridge-control"
STATE_ROOT: Final = ".openminis-bridge-control"
ENTRYPOINT: Final = "openminis_bridge_control.py"
MAX_ARCHIVE_BYTES: Final = 1_048_576
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
TAILNET: Final = ipaddress.IPv4Network("100.64.0.0/10")


@dataclass(frozen=True, slots=True)
class InstallError(Exception):
    """One stable non-secret installation failure."""

    code: str

    def __str__(self) -> str:
        return self.code


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise InstallError(code)


def _tailnet_address(raw: str) -> str:
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as error:
        raise InstallError("NETWORK_IDENTITY") from error
    _need(address in TAILNET, "NETWORK_IDENTITY")
    return str(address)


def _manifest() -> dict[str, tuple[int, str]]:
    _need(hashlib.sha256(MANIFEST_JSON.encode()).hexdigest() == MANIFEST_SHA256, "MANIFEST")
    try:
        raw = json.loads(MANIFEST_JSON)
    except json.JSONDecodeError as error:
        raise InstallError("MANIFEST") from error
    _need(isinstance(raw, dict), "MANIFEST")
    result: dict[str, tuple[int, str]] = {}
    for name, identity in raw.items():
        safe_name = isinstance(name, str) and PurePosixPath(name).as_posix() == name
        safe_parts = safe_name and 1 <= len(PurePosixPath(name).parts) <= 2
        safe_identity = (
            isinstance(identity, list)
            and len(identity) == 2
            and isinstance(identity[0], int)
            and isinstance(identity[1], str)
            and len(identity[1]) == 64
        )
        _need(bool(safe_parts and safe_identity), "MANIFEST")
        result[name] = (identity[0], identity[1])
    return result


def _archive_files(expected: dict[str, tuple[int, str]]) -> dict[str, bytes]:
    try:
        archive = gzip.decompress(base64.b64decode(ARCHIVE_B64, validate=True))
    except (ValueError, gzip.BadGzipFile) as error:
        raise InstallError("ARCHIVE") from error
    _need(0 < len(archive) <= MAX_ARCHIVE_BYTES, "ARCHIVE")
    files: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            members = bundle.getmembers()
            _need(tuple(member.name for member in members) == tuple(expected), "ARCHIVE")
            for member in members:
                size, digest = expected[member.name]
                _need(member.isreg() and member.mode == PRIVATE_FILE_MODE, "ARCHIVE")
                stream = bundle.extractfile(member)
                _need(stream is not None, "ARCHIVE")
                content = stream.read(MAX_ARCHIVE_BYTES + 1)
                _need(len(content) == size, "ARCHIVE")
                _need(hashlib.sha256(content).hexdigest() == digest, "ARCHIVE")
                files[member.name] = content
    except (OSError, tarfile.TarError) as error:
        raise InstallError("ARCHIVE") from error
    return files


def _private_write(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
    except OSError as error:
        raise InstallError("WRITE") from error
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            _ = stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        metadata = path.lstat()
        _need(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and metadata.st_nlink == 1
            and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE,
            "WRITE",
        )
    except OSError as error:
        raise InstallError("WRITE") from error


def _run_lifecycle(entrypoint: Path, command: str, home: Path) -> str:
    environment = {
        "HOME": str(home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "TMPDIR": "/tmp",  # noqa: S108 -- fixed Android Minis runtime temp root.
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(entrypoint), command],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
            env=environment,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InstallError("LIFECYCLE") from error
    _need(completed.returncode == 0 and len(completed.stdout) <= 256, "LIFECYCLE")
    return completed.stdout.strip()


def _install() -> dict[str, str | int | bool]:
    _need(sys.platform.startswith("linux") and sys.version_info >= (3, 12), "RUNTIME")
    _need(len(sys.argv) == 3 and sys.argv[1] == "INSTALL_ONCE", "APPROVAL")
    _need(secrets.compare_digest(sys.argv[2], APPROVAL_BINDING), "APPROVAL")
    phone = _tailnet_address(PHONE_IPV4)
    trusted_mac = _tailnet_address(TRUSTED_MAC_IPV4)
    _need(phone != trusted_mac and 1 <= PORT <= 65_535, "NETWORK_IDENTITY")
    expected = _manifest()
    files = _archive_files(expected)
    home = Path.home().resolve()
    install_root = home / INSTALL_ROOT
    state_root = home / STATE_ROOT
    _need(not install_root.exists() and not install_root.is_symlink(), "INSTALL_EXISTS")
    _need(not state_root.exists() and not state_root.is_symlink(), "STATE_EXISTS")
    try:
        install_root.parent.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
        install_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        (install_root / "openminis_bridge_control_core").mkdir(mode=PRIVATE_DIRECTORY_MODE)
        state_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    except OSError as error:
        raise InstallError("DIRECTORY") from error
    for name, content in files.items():
        _private_write(install_root / name, content)
    config = {
        "phone_ipv4": phone,
        "port": PORT,
        "schema": 1,
        "trusted_mac_ipv4": trusted_mac,
    }
    encoded_config = json.dumps(config, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    _private_write(state_root / "bridge.json", encoded_config)
    _private_write(state_root / "token", secrets.token_hex(32).encode() + b"\n")
    entrypoint = install_root / ENTRYPOINT
    started = _run_lifecycle(entrypoint, "start", home)
    _need(started.startswith("started PID "), "LIFECYCLE")
    running = _run_lifecycle(entrypoint, "status", home)
    _need(running.startswith("running PID "), "LIFECYCLE")
    return {
        "version": VERSION,
        "status": "INSTALLED_RUNNING",
        "files_created": len(files) + 2,
        "bridge_started": True,
        "token_disclosed": False,
    }


def _main() -> int:
    try:
        result = _install()
        envelope = {"ok": True, "action": "install", "result": result}
        code = 0
    except InstallError as error:
        envelope = {
            "ok": False,
            "action": "install",
            "error": {"code": error.code, "message": "installation stopped safely"},
        }
        code = 1
    _ = sys.stdout.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(_main())
