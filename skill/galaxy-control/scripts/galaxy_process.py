"""Bounded non-shell process execution shared by Galaxy Control adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Final, Literal, Protocol, TypeAlias

OUTPUT_LIMIT: Final = 1_048_576
COMMAND_TIMEOUT_SECONDS: Final = 12.0
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]
Controller: TypeAlias = Literal["openminis", "adb", "scrcpy"]
Transport: TypeAlias = Literal["tailscale_http", "adb", "adb_tcpip", "adb_usb"]
RouteRole: TypeAlias = Literal["observe", "act", "connect", "system", "record"]


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


@dataclass(frozen=True, slots=True)
class RouteMetadata:
    """Fixed controller and verification evidence for one reviewed action."""

    controller: Controller
    transport: Transport
    role: RouteRole
    verification_required: bool
    verify_with: tuple[Controller, ...] = ()

    def to_json(self) -> JsonObject:
        """Return stable route metadata suitable for a result envelope."""
        return {
            "controller": self.controller,
            "transport": self.transport,
            "role": self.role,
            "verification_required": self.verification_required,
            "verify_with": list(self.verify_with),
        }


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


def with_route(
    result: JsonObject,
    route: RouteMetadata,
) -> JsonObject:
    """Attach fixed route metadata inside the stable result envelope."""
    return {**result, "route": route.to_json()}


def error_envelope(action: str, code: str, message: str) -> JsonObject:
    """Create the stable failure envelope."""
    return {"ok": False, "action": action, "error": {"code": code, "message": message}}
