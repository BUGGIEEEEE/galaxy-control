#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""Standard-library bootstrap for installing uv on a new Mac."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded process result."""

    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    """Run one exact bootstrap command."""

    def __call__(self, argv: tuple[str, ...]) -> CommandResult:
        """Execute one reviewed argv tuple."""
        ...


@dataclass(frozen=True, slots=True)
class BootstrapRuntime:
    """Injectable process and executable discovery boundaries."""

    runner: Runner
    which: Callable[[str], str | None]


def run_command(argv: tuple[str, ...]) -> CommandResult:
    """Run one reviewed installer command without a shell."""
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CommandResult(127, "", "bootstrap command unavailable")
    return CommandResult(completed.returncode, completed.stdout[:65_536], completed.stderr[:65_536])


def _status(runtime: BootstrapRuntime) -> JsonObject:
    uv = runtime.which("uv")
    brew = runtime.which("brew")
    if uv is not None:
        return {"status": "READY", "uv_installed": True, "updates_existing_uv": False}
    if brew is None:
        return {
            "status": "NEEDS_USER_ACTION",
            "uv_installed": False,
            "install_command": None,
            "user_actions": ["install_homebrew_or_uv_manually"],
            "updates_existing_uv": False,
        }
    return {
        "status": "NEEDS_APPROVAL",
        "uv_installed": False,
        "install_command": [brew, "install", "uv"],
        "user_actions": [],
        "updates_existing_uv": False,
    }


def _success(action: str, result: JsonObject) -> JsonObject:
    return {"ok": True, "action": action, "result": result}


def _error(action: str, code: str, message: str) -> JsonObject:
    return {"ok": False, "action": action, "error": {"code": code, "message": message}}


def execute(argv: tuple[str, ...], runtime: BootstrapRuntime) -> tuple[JsonObject, int]:
    """Diagnose or install only missing uv through an existing Homebrew."""
    action = argv[0] if argv else "unknown"
    match argv:  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
        case ("doctor",):
            return _success(action, _status(runtime)), 0
        case ("apply",):
            return _error(action, "approval_required", "rerun with --approved"), 1
        case ("apply", "--approved"):
            status = _status(runtime)
            if status["uv_installed"] is True:
                return _success(action, {**status, "installed": False}), 0
            brew = runtime.which("brew")
            if brew is None:
                return _error(action, "homebrew_missing", "install Homebrew or uv manually"), 1
            result = runtime.runner((brew, "install", "uv"))
            if result.returncode != 0:
                return _error(action, "uv_install_failed", "approved uv installation failed"), 1
            return _success(action, {"status": "READY", "installed": True}), 0
        case _:
            return _error(action, "invalid_request", "use doctor or apply --approved"), 1


def main(argv: tuple[str, ...] | None = None) -> int:
    """Print one stable JSON envelope."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    envelope, exit_code = execute(args, BootstrapRuntime(run_command, shutil.which))
    _ = sys.stdout.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
