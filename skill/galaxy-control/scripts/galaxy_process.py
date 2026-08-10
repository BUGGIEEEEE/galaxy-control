"""Bounded non-shell process execution shared by Galaxy Control adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Final, Protocol, TypeAlias

OUTPUT_LIMIT: Final = 1_048_576
COMMAND_TIMEOUT_SECONDS: Final = 12.0
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded output from one literal argv call."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        """Return whether the process completed successfully."""
        return self.returncode == 0


class Runner(Protocol):
    """Execute one reviewed argv tuple."""

    def __call__(self, argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult: ...


def run_command(argv: tuple[str, ...], *, stdin: str | None = None) -> CommandResult:
    """Run exact argv with bounded output, timeout, and no shell."""
    try:
        completed = subprocess.run(
            argv,
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return CommandResult(127, "", "command not found")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "command timed out")
    return CommandResult(
        completed.returncode,
        completed.stdout[:OUTPUT_LIMIT],
        completed.stderr[:OUTPUT_LIMIT],
    )


def success_envelope(action: str, result: JsonObject) -> JsonObject:
    """Create the stable success envelope."""
    return {"ok": True, "action": action, "result": result}


def error_envelope(action: str, code: str, message: str) -> JsonObject:
    """Create the stable failure envelope."""
    return {"ok": False, "action": action, "error": {"code": code, "message": message}}
