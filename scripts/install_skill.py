#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""Install the bundled skill without overwriting an existing installation."""

from __future__ import annotations

import json
import shutil
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


def install(source: Path, destination: Path) -> Path:
    """Atomically copy one valid bundled skill into a new exact destination."""
    if source.is_symlink() or not source.is_dir() or not (source / "SKILL.md").is_file():
        raise InstallError("source_invalid", "bundled galaxy-control skill is invalid")
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


def main(argv: tuple[str, ...] | None = None) -> int:
    """Install only after an explicit command-line approval marker."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    action = "install"
    if args != ("--approved",):
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
            installed = install(source, destination)
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
                "result": {"installed": True, "path": str(installed)},
            }
            exit_code = 0
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
