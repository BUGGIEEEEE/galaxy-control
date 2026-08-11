"""Identity-checked process control for the OpenMinis bridge lifecycle."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Final, Protocol

from openminis_bridge_control_core import BridgeError

if TYPE_CHECKING:
    from collections.abc import Callable

IS_LINUX: Final = sys.platform.startswith("linux")


class _StartedProcess(Protocol):
    """Expose only child controls required during cleanup."""

    pid: int

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


def terminate_started(process: _StartedProcess) -> None:
    """Kill and reap a child started by the current lifecycle process."""
    cleanup_error: OSError | None = None
    needs_direct_kill = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
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
        raise BridgeError(1, "cleanup_failed", "started bridge could not be reaped") from error
    if cleanup_error is not None:
        raise BridgeError(
            1, "cleanup_failed", "started bridge could not be reaped"
        ) from cleanup_error


def _open_pidfd(pid: int) -> int:
    try:
        return os.pidfd_open(pid)
    except AttributeError as error:
        raise BridgeError(
            1, "pidfd_unavailable", "kernel process handles are unavailable"
        ) from error
    except ProcessLookupError as error:
        raise BridgeError(1, "identity_mismatch", "PID identity does not match bridge") from error
    except OSError as error:
        raise BridgeError(
            1, "pidfd_unavailable", "kernel process handle could not be opened"
        ) from error


def _signal_pidfd(handle: int) -> None:
    try:
        signal.pidfd_send_signal(handle, signal.SIGTERM)
    except ProcessLookupError:
        return
    except AttributeError as error:
        raise BridgeError(
            1, "pidfd_unavailable", "kernel process handles are unavailable"
        ) from error
    except OSError as error:
        raise BridgeError(1, "stop_failed", "bridge could not be signalled") from error


def _wait_pidfd(handle: int, timeout: float) -> bool:
    try:
        ready, _, _ = select.select([handle], [], [], timeout)
    except OSError as error:
        raise BridgeError(1, "stop_failed", "bridge exit could not be observed") from error
    return bool(ready)


def _close_pidfd(handle: int) -> None:
    try:
        os.close(handle)
    except OSError as error:
        raise BridgeError(1, "stop_failed", "kernel process handle could not be closed") from error


def _stop_by_pid(pid: int, owns_process: Callable[[], bool], timeout: float) -> bool:
    if not owns_process():
        raise BridgeError(1, "identity_mismatch", "PID identity does not match bridge")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError as error:
        raise BridgeError(1, "stop_failed", "bridge could not be signalled") from error
    deadline = time.monotonic() + timeout
    while owns_process() and time.monotonic() < deadline:
        time.sleep(0.05)
    return not owns_process()


def stop_owned_process(pid: int, owns_process: Callable[[], bool], timeout: float) -> bool:
    """Signal and observe one identity-checked process without Linux PID reuse."""
    if not IS_LINUX:
        return _stop_by_pid(pid, owns_process, timeout)
    handle = _open_pidfd(pid)
    try:
        if not owns_process():
            raise BridgeError(1, "identity_mismatch", "PID identity does not match bridge")
        _signal_pidfd(handle)
        return _wait_pidfd(handle, timeout)
    finally:
        _close_pidfd(handle)
