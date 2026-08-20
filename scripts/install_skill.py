#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""Install the bundled skill without overwriting an existing installation."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstallError(Exception):
    """Safe installation failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class UpgradeResult:
    """Installed path and retained rollback copy."""

    installed: Path
    backup: Path


RENAME_SWAP = 0x00000002


def _atomic_swap(staged: Path, destination: Path) -> None:
    if sys.platform != "darwin":
        raise OSError(errno.ENOTSUP, "atomic skill upgrade requires macOS")
    library = ctypes.CDLL(None, use_errno=True)
    renamex_np = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint,
    )(("renamex_np", library))
    if renamex_np(os.fsencode(staged), os.fsencode(destination), RENAME_SWAP) != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            str(staged),
            str(destination),
        )


def _validate_source(source: Path) -> None:
    if source.is_symlink() or not source.is_dir() or not (source / "SKILL.md").is_file():
        raise InstallError("source_invalid", "bundled galaxy-control skill is invalid")


def install(source: Path, destination: Path) -> Path:
    """Atomically copy one valid bundled skill into a new exact destination."""
    _validate_source(source)
    if destination.exists() or destination.is_symlink():
        raise InstallError("destination_exists", "galaxy-control is already installed")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".galaxy-control-install-", dir=destination.parent))
    staged = work / "galaxy-control"
    try:
        _ = shutil.copytree(source, staged, symlinks=False)
        _ = staged.replace(destination)
    except OSError as error:
        raise InstallError("install_failed", "skill files could not be installed") from error
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return destination


def _new_backup_path(parent: Path) -> Path:
    try:
        parent.mkdir(mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        backup = Path(tempfile.mkdtemp(prefix="galaxy-control-", dir=parent))
        backup.rmdir()
    except OSError as error:
        raise InstallError("upgrade_failed", "rollback path could not be prepared") from error
    return backup


def _secure_legacy_cache_root(directory: Path) -> None:
    """Migrate the user-owned v0.4 cache parent to the v0.5 privacy contract."""
    try:
        initial = directory.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise InstallError(
            "cache_migration_failed",
            "legacy Galaxy Control cache could not be inspected",
        ) from error
    if not stat.S_ISDIR(initial.st_mode) or initial.st_uid != os.getuid():
        raise InstallError(
            "cache_migration_unsafe",
            "legacy Galaxy Control cache is not a user-owned real directory",
        )
    try:
        descriptor = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as error:
        raise InstallError(
            "cache_migration_failed",
            "legacy Galaxy Control cache could not be opened safely",
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_dev != initial.st_dev
            or metadata.st_ino != initial.st_ino
        ):
            raise InstallError(
                "cache_migration_unsafe",
                "legacy Galaxy Control cache changed before migration",
            )
        try:
            os.fchmod(descriptor, 0o700)
            migrated = os.fstat(descriptor)
            path_metadata = directory.lstat()
        except OSError as error:
            raise InstallError(
                "cache_migration_failed",
                "legacy Galaxy Control cache could not be secured",
            ) from error
        if (
            not stat.S_ISDIR(migrated.st_mode)
            or migrated.st_uid != os.getuid()
            or stat.S_IMODE(migrated.st_mode) != 0o700
        ):
            raise InstallError(
                "cache_migration_failed",
                "legacy Galaxy Control cache did not become private",
            )
        if (
            not stat.S_ISDIR(path_metadata.st_mode)
            or path_metadata.st_uid != os.getuid()
            or path_metadata.st_dev != migrated.st_dev
            or path_metadata.st_ino != migrated.st_ino
        ):
            raise InstallError(
                "cache_migration_unsafe",
                "legacy Galaxy Control cache path changed during migration",
            )
    finally:
        os.close(descriptor)


def upgrade(source: Path, destination: Path) -> UpgradeResult:
    """Replace one real installed skill while retaining an exact rollback copy."""
    _validate_source(source)
    if (
        destination.is_symlink()
        or not destination.is_dir()
        or not (destination / "SKILL.md").is_file()
    ):
        raise InstallError("destination_invalid", "installed galaxy-control skill is invalid")
    backup_parent = destination.parent / ".galaxy-control-backups"
    try:
        destination.chmod(0o700)
    except OSError as error:
        raise InstallError("upgrade_failed", "installed skill could not be secured") from error
    backup = _new_backup_path(backup_parent)
    try:
        _ = shutil.copytree(source, backup, symlinks=False)
        _atomic_swap(backup, destination)
    except OSError as error:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        raise InstallError("upgrade_failed", "skill files could not be upgraded") from error
    return UpgradeResult(destination, backup)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Install only after an explicit command-line approval marker."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    action = "upgrade" if args and args[0] == "--upgrade" else "install"
    if args not in {("--approved",), ("--upgrade", "--approved")}:
        envelope = {
            "ok": False,
            "action": action,
            "error": {"code": "approval_required", "message": "rerun with --approved"},
        }
        exit_code = 1
    else:
        repository = Path(__file__).resolve().parent.parent
        source = repository / "skill" / "galaxy-control"
        destination = Path.home() / ".codex" / "skills" / "galaxy-control"
        try:
            if action == "upgrade":
                _secure_legacy_cache_root(Path.home() / "Library" / "Caches" / "galaxy-control")
                upgraded = upgrade(source, destination)
                installed = upgraded.installed
                backup: str | None = str(upgraded.backup)
            else:
                installed = install(source, destination)
                backup = None
        except InstallError as error:
            envelope = {
                "ok": False,
                "action": action,
                "error": {"code": error.code, "message": error.message},
            }
            exit_code = 1
        else:
            envelope = {
                "ok": True,
                "action": action,
                "result": {
                    "installed": True,
                    "path": str(installed),
                    "backup": backup,
                },
            }
            exit_code = 0
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
