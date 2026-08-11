"""Bounded execution of fixed OpenMinis device commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from typing import Final, final

from .protocol import Action, BridgeError, validate_cli_output
from .requests import CommandRequest, Executable, fixed_request

MAX_OUTPUT_BYTES: Final = 65_536
MAX_UI_DUMP_OUTPUT_BYTES: Final = 1_048_576
MIN_COMMAND_TIMEOUT_SECONDS: Final = 0.1
MAX_COMMAND_TIMEOUT_SECONDS: Final = 120.0
LIMIT_RUNNER: Final = (
    "import os,resource,sys;"
    f"resource.setrlimit(resource.RLIMIT_FSIZE,({MAX_UI_DUMP_OUTPUT_BYTES},{MAX_UI_DUMP_OUTPUT_BYTES}));"
    "os.execv(sys.argv[1],sys.argv[1:])"
)


def _command_timeout() -> float:
    raw = os.environ.get("OPENMINIS_BRIDGE_COMMAND_TIMEOUT_SECONDS", "10")
    try:
        timeout = float(raw)
    except ValueError as error:
        raise BridgeError(500, "invalid_config", "command timeout is invalid") from error
    if not MIN_COMMAND_TIMEOUT_SECONDS <= timeout <= MAX_COMMAND_TIMEOUT_SECONDS:
        raise BridgeError(500, "invalid_config", "command timeout is outside safe bounds")
    return timeout


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    cleanup_error: OSError | None = None
    needs_direct_kill = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        _ = process.poll()
        needs_direct_kill = True
    except OSError as error:
        cleanup_error = error
        needs_direct_kill = True
    if needs_direct_kill:
        try:
            process.kill()
        except OSError as error:
            cleanup_error = error
    try:
        _ = process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BridgeError(500, "cleanup_failed", "device command could not be reaped") from error
    if cleanup_error is not None:
        raise BridgeError(
            500, "cleanup_failed", "device command could not be reaped"
        ) from cleanup_error


@final
class CommandRunner:
    """Run one fixed command at a time and own the active child for shutdown."""

    def __init__(self, shizuku_cli_path: str | None, a11y_cli_path: str | None = None) -> None:
        """Pin only the two reviewed device CLI executables."""
        self._shizuku_cli_path = shizuku_cli_path
        self._a11y_cli_path = a11y_cli_path
        self._active_process: subprocess.Popen[bytes] | None = None

    def terminate(self) -> None:
        """Kill the active fixed-command process group, if one is running."""
        if self._active_process is not None:
            _terminate_group(self._active_process)

    def run(self, command: Action | CommandRequest) -> str:
        """Run one validated literal action and return its raw JSON envelope."""
        request = fixed_request(command) if isinstance(command, Action) else command
        if request.executable is Executable.NONE:
            return '{"status":"ok"}'
        cli_path = (
            self._shizuku_cli_path
            if request.executable is Executable.SHIZUKU
            else self._a11y_cli_path
        )
        if cli_path is None:
            name = (
                "android-shizuku-cli"
                if request.executable is Executable.SHIZUKU
                else "android-a11y-cli"
            )
            raise BridgeError(503, "cli_unavailable", f"{name} was not found")
        output_limit = (
            MAX_UI_DUMP_OUTPUT_BYTES if request.action is Action.UI_DUMP else MAX_OUTPUT_BYTES
        )
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", "-c", LIMIT_RUNNER, cli_path, *request.argv],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
            self._active_process = process
            try:
                try:
                    return_code = process.wait(timeout=_command_timeout())
                except subprocess.TimeoutExpired as error:
                    _terminate_group(process)
                    raise BridgeError(504, "command_timeout", "device command timed out") from error
            finally:
                self._active_process = None
            _ = output.seek(0)
            raw = output.read(output_limit + 1)
        if len(raw) > output_limit:
            raise BridgeError(502, "output_too_large", "device command output exceeded the limit")
        if return_code != 0:
            raise BridgeError(
                502, "command_failed", f"device command failed with exit code {return_code}"
            )
        return validate_cli_output(raw.strip())
