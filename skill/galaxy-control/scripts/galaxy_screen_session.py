"""Start and stop only adapter-owned fixed-profile scrcpy processes."""

from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from galaxy_adb import AdbError, AdbRuntime, list_devices
from galaxy_process import JsonObject, Runner, run_command
from galaxy_recording import (
    RecordingPaths,
    cleanup_recording,
    finalize_recording,
    prepare_recording,
)
from galaxy_screen_core import (
    ScreenError,
    ScreenProfile,
    ScreenRequest,
    build_scrcpy_argv,
    select_device,
)
from galaxy_screen_state import (
    ProcessIdentity,
    ScreenState,
    identity_matches,
    load_state,
    remove_state,
    state_directory,
    write_state,
)
from scrcpy_app import ensure_app_executable

STARTUP_GRACE_SECONDS: Final = 0.8
STOP_GRACE_SECONDS: Final = 10.0
REQUIRED_OPTIONS: Final = (
    "--serial",
    "--no-control",
    "--no-audio",
    "--no-clipboard-autosync",
    "--record",
    "--no-playback",
    "--window-title",
)


@dataclass(frozen=True, slots=True)
class ScreenRuntime:
    """Enrolled ADB and installed scrcpy boundaries."""

    adb: AdbRuntime
    scrcpy_path: str | None
    runner: Runner


def process_identity(pid: int) -> ProcessIdentity | None:
    """Read exact macOS process start and full command identity."""
    start = run_command(("/bin/ps", "-p", str(pid), "-o", "lstart="))
    command = run_command(("/bin/ps", "-ww", "-p", str(pid), "-o", "command="))
    if (
        not start.succeeded
        or not command.succeeded
        or not start.stdout.strip()
        or not command.stdout.strip()
    ):
        return None
    return ProcessIdentity(start.stdout.strip(), command.stdout.strip())


def _scrcpy_executable(runtime: ScreenRuntime) -> str:
    if runtime.scrcpy_path is None:
        raise ScreenError("scrcpy_not_installed", "scrcpy executable was not found")
    help_result = runtime.runner((runtime.scrcpy_path, "--help"))
    if not help_result.succeeded or any(
        option not in help_result.stdout for option in REQUIRED_OPTIONS
    ):
        raise ScreenError("scrcpy_option_unsupported", "scrcpy lacks a required safe option")
    try:
        return ensure_app_executable(runtime.scrcpy_path, state_directory())
    except OSError as error:
        raise ScreenError(
            "scrcpy_start_failed", "scrcpy app identity could not be prepared"
        ) from error


def doctor(runtime: ScreenRuntime) -> JsonObject:
    """Return read-only ADB and scrcpy path availability."""
    try:
        devices = list_devices(runtime.adb)
    except AdbError as error:
        adb_result: JsonObject = {"ready": False, "error": error.code, "devices": []}
    else:
        adb_result = {
            "ready": True,
            "devices": [
                {
                    "serial": device.serial,
                    "state": device.state,
                    "transport": device.transport,
                    "model": device.model,
                }
                for device in devices
            ],
        }
    scrcpy_result: JsonObject = {
        "installed": runtime.scrcpy_path is not None,
        "path": runtime.scrcpy_path,
    }
    return {"adb": adb_result, "scrcpy": scrcpy_result}


def _recording_from_state(state: ScreenState) -> RecordingPaths | None:
    if state.profile != "record":
        return None
    values = (state.output_path, state.record_work_dir, state.record_temp_path)
    if any(value is None for value in values):
        raise ScreenError("process_identity_mismatch", "record paths are missing")
    output, work, temp = values
    if output is None or work is None or temp is None:
        raise ScreenError("process_identity_mismatch", "record paths are missing")
    return RecordingPaths(Path(output), Path(work), Path(temp))


def start(request: ScreenRequest, runtime: ScreenRuntime) -> JsonObject:
    """Start one managed fixed-profile scrcpy process."""
    if request.action not in {"view", "control", "record"}:
        raise ScreenError("invalid_request", "start requires a scrcpy profile")
    profile = cast("ScreenProfile", request.action)
    existing = load_state()
    if existing is not None:
        identity = process_identity(existing.pid)
        if identity is not None and identity_matches(existing, identity):
            raise ScreenError("scrcpy_already_running", "a managed scrcpy session is running")
        raise ScreenError("process_identity_mismatch", "stale screen state requires review")
    executable = _scrcpy_executable(runtime)
    device = select_device(runtime.adb.profile, list_devices(runtime.adb), request.serial)
    recording = prepare_recording(request.output)
    session_id = uuid.uuid4().hex
    stderr_path = state_directory() / f"scrcpy-{session_id}.stderr"
    argv = build_scrcpy_argv(
        executable,
        profile,
        device.serial,
        session_id,
        recording.temp_path if recording is not None else None,
    )
    try:
        with stderr_path.open("xb") as stderr_handle:
            stderr_path.chmod(0o600)
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                cwd="/",
                start_new_session=True,
                shell=False,
            )
    except OSError as error:
        cleanup_recording(recording)
        raise ScreenError("scrcpy_start_failed", "scrcpy could not be started") from error
    time.sleep(STARTUP_GRACE_SECONDS)
    if process.poll() is not None:
        cleanup_recording(recording)
        raise ScreenError("scrcpy_exited_early", "scrcpy exited before startup completed")
    identity = process_identity(process.pid)
    if identity is None:
        process.terminate()
        cleanup_recording(recording)
        raise ScreenError("scrcpy_start_failed", "scrcpy process identity could not be read")
    state = ScreenState(
        schema_version=1,
        session_id=session_id,
        pid=process.pid,
        profile=profile,
        serial=device.serial,
        model=runtime.adb.profile.expected_model,
        executable=executable,
        argv=argv,
        ps_start=identity.ps_start,
        ps_command=identity.ps_command,
        stderr_path=str(stderr_path),
        output_path=str(recording.output) if recording is not None else None,
        record_work_dir=str(recording.work_directory) if recording is not None else None,
        record_temp_path=str(recording.temp_path) if recording is not None else None,
    )
    write_state(state)
    return {
        "profile": profile,
        "pid": process.pid,
        "serial": device.serial,
        "started": True,
        "read_only": profile in {"view", "record"},
        "audio": False,
        "clipboard_autosync": False,
        "verification_required": profile == "control",
    }


def _wait_until_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process_identity(pid) is None:
            return True
        time.sleep(0.1)
    return process_identity(pid) is None


def stop() -> JsonObject:
    """Stop only the exact managed process and finalize its recording."""
    state = load_state()
    if state is None:
        raise ScreenError("scrcpy_not_running", "no managed scrcpy session exists")
    identity = process_identity(state.pid)
    already_exited = identity is None
    if identity is not None:
        if not identity_matches(state, identity):
            raise ScreenError("process_identity_mismatch", "stored PID belongs to another process")
        os.kill(state.pid, signal.SIGINT)
        if not _wait_until_gone(state.pid, STOP_GRACE_SECONDS):
            current = process_identity(state.pid)
            if current is None or not identity_matches(state, current):
                raise ScreenError(
                    "process_identity_mismatch", "process identity changed during stop"
                )
            os.kill(state.pid, signal.SIGTERM)
            if not _wait_until_gone(state.pid, 3.0):
                raise ScreenError("scrcpy_stop_failed", "managed scrcpy did not stop")
    paths = _recording_from_state(state)
    recording = finalize_recording(paths) if paths is not None else None
    remove_state()
    stderr_path = Path(state.stderr_path)
    if (
        stderr_path.parent == state_directory()
        and stderr_path.name == f"scrcpy-{state.session_id}.stderr"
    ):
        stderr_path.unlink(missing_ok=True)
    return {
        "profile": state.profile,
        "pid": state.pid,
        "serial": state.serial,
        "stopped": True,
        "already_exited": already_exited,
        "recording": recording,
    }
