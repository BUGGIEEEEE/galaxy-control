"""Private owner state and detached-process lifecycle for Control v2."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import select
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from openminis_bridge_control_core import BridgeError, load_network
from openminis_bridge_control_core.network import STATE_DIR
from openminis_bridge_control_process import stop_owned_process, terminate_started

TOKEN_BYTES: Final = 32
START_TIMEOUT_SECONDS: Final = 5
STOP_TIMEOUT_SECONDS: Final = 2
LOG_MAX_BYTES: Final = 1_000_000
PROCESS_START_FIELD_INDEX: Final = 19
PRIVATE_FILE_MODE: Final = 0o600
HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdef")
SCRIPT_PATH: Final = Path(__file__).with_name("openminis_bridge_control.py").resolve()


@dataclass(frozen=True, slots=True)
class _PidState:
    pid: int
    start_marker: str
    launch_id: str
    argv_digest: str

    def encode(self) -> str:
        return f"{self.pid}\n{self.start_marker}\n{self.launch_id}\n{self.argv_digest}\n"


def _private_write(path: Path, content: str, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, PRIVATE_FILE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        _ = stream.write(content)


def _prepare_state() -> Path:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    return STATE_DIR


def _is_64_hex(value: str) -> bool:
    return len(value) == TOKEN_BYTES * 2 and all(character in HEX_DIGITS for character in value)


def initialize_token() -> None:
    """Create the private owner token exactly once."""
    _private_write(
        _prepare_state() / "token", secrets.token_hex(TOKEN_BYTES) + "\n", exclusive=True
    )


def read_token() -> str:
    """Read one canonical 256-bit ASCII hexadecimal token."""
    try:
        stored = (STATE_DIR / "token").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BridgeError(1, "token_unavailable", "run init-token first") from error
    token = stored[:-1]
    if stored.endswith("\n") and _is_64_hex(token):
        return token
    raise BridgeError(1, "token_unavailable", "run init-token first")


def _read_pid_state() -> _PidState:
    try:
        lines = (STATE_DIR / "bridge.pid").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise BridgeError(
            1, "pid_unavailable", "bridge PID identity file is unavailable"
        ) from error
    if len(lines) != 4:
        raise BridgeError(1, "pid_unavailable", "bridge PID identity file is invalid")
    try:
        pid = int(lines[0])
    except ValueError as error:
        raise BridgeError(1, "pid_unavailable", "bridge PID identity file is invalid") from error
    start_marker, launch_id, argv_digest = lines[1], lines[2], lines[3]
    valid = pid > 1 and bool(start_marker) and _is_64_hex(launch_id) and _is_64_hex(argv_digest)
    if not valid:
        raise BridgeError(1, "pid_unavailable", "bridge PID identity file is invalid")
    return _PidState(pid, start_marker, launch_id, argv_digest)


def _validate_launch_argv(arguments: list[bytes], launch_id: str, config_sha256: str) -> None:
    valid = (
        len(arguments) == 12
        and arguments[1:7]
        == [b"-E", b"-s", b"-B", os.fsencode(SCRIPT_PATH), b"serve", b"--config-sha256"]
        and hmac.compare_digest(arguments[7], os.fsencode(config_sha256))
        and arguments[8:11:2] == [b"--ready-fd", b"--launch-id"]
        and hmac.compare_digest(arguments[11], os.fsencode(launch_id))
    )
    if not valid:
        raise ValueError


def _observe_process(pid: int, launch_id: str, config_sha256: str) -> tuple[str, str]:
    proc_stat = Path(f"/proc/{pid}/stat")
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_stat.exists() and proc_cmdline.exists():
        fields = proc_stat.read_bytes().rpartition(b") ")[2].split()
        start_marker = f"linux:{int(fields[PROCESS_START_FIELD_INDEX])}"
        arguments = proc_cmdline.read_bytes().removesuffix(b"\0").split(b"\0")
    else:
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
            shell=False,
        )
        fields = result.stdout.strip().split(maxsplit=5)
        if result.returncode != 0 or len(fields) != 6:
            raise ProcessLookupError(pid)
        start_marker = "ps:" + " ".join(fields[:5])
        arguments = [os.fsencode(part) for part in shlex.split(fields[5])]
    _validate_launch_argv(arguments, launch_id, config_sha256)
    return start_marker, hashlib.sha256(b"\0".join(arguments)).hexdigest()


def _owns_process(state: _PidState, config_sha256: str) -> bool:
    try:
        start_marker, argv_digest = _observe_process(state.pid, state.launch_id, config_sha256)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return False
    return start_marker == state.start_marker and hmac.compare_digest(
        argv_digest, state.argv_digest
    )


def _open_log_fd() -> int:
    try:
        fd = os.open(
            _prepare_state() / "bridge.log",
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
    except (AttributeError, OSError) as error:
        raise BridgeError(1, "start_failed", "bridge log state is unsafe") from error
    metadata = os.fstat(fd)
    safe = (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and metadata.st_nlink == 1
        and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE
    )
    if not safe:
        os.close(fd)
        raise BridgeError(1, "start_failed", "bridge log state is unsafe")
    if metadata.st_size > LOG_MAX_BYTES:
        os.ftruncate(fd, 0)
    return fd


def _check_existing_pid(pid_path: Path, config_sha256: str) -> None:
    if not pid_path.exists():
        return
    state = _read_pid_state()
    if _owns_process(state, config_sha256):
        raise BridgeError(1, "already_running", "bridge is already running")
    try:
        os.kill(state.pid, 0)
    except ProcessLookupError:
        pid_path.unlink()
        return
    except PermissionError as error:
        raise BridgeError(1, "identity_mismatch", "PID identity does not match bridge") from error
    raise BridgeError(1, "identity_mismatch", "PID identity does not match bridge")


def start() -> int:
    """Start one detached bridge from the exact private network config."""
    _ = read_token()
    config_sha256 = load_network().config_sha256
    pid_path = _prepare_state() / "bridge.pid"
    _check_existing_pid(pid_path, config_sha256)
    ready_read, ready_write = os.pipe()
    launch_id = secrets.token_hex(TOKEN_BYTES)
    command = [sys.executable, "-E", "-s", "-B", str(SCRIPT_PATH), "serve"]
    command += ["--config-sha256", config_sha256, "--ready-fd", str(ready_write)]
    command += ["--launch-id", launch_id]
    log_fd = _open_log_fd()
    with os.fdopen(log_fd, "ab", buffering=0) as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            pass_fds=(ready_write,),
            start_new_session=True,
            shell=False,
        )
    os.close(ready_write)
    try:
        ready, _, _ = select.select([ready_read], [], [], START_TIMEOUT_SECONDS)
        signal_byte = os.read(ready_read, 1) if ready else b""
    except OSError as error:
        terminate_started(process)
        raise BridgeError(1, "start_failed", "bridge failed to become ready") from error
    finally:
        os.close(ready_read)
    if signal_byte != b"R" or process.poll() is not None:
        terminate_started(process)
        raise BridgeError(1, "start_failed", "bridge failed to become ready")
    try:
        start_marker, argv_digest = _observe_process(process.pid, launch_id, config_sha256)
        _private_write(
            pid_path,
            _PidState(process.pid, start_marker, launch_id, argv_digest).encode(),
            exclusive=True,
        )
    except FileExistsError:
        terminate_started(process)
        raise BridgeError(1, "start_failed", "bridge PID state changed during startup") from None
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as error:
        terminate_started(process)
        raise BridgeError(1, "start_failed", "bridge PID state could not be persisted") from error
    return process.pid


def stop() -> int:
    """Signal an owned bridge and report success only after confirmed exit."""
    config_sha256 = load_network().config_sha256
    state = _read_pid_state()
    exited = stop_owned_process(
        state.pid,
        lambda: _owns_process(state, config_sha256),
        STOP_TIMEOUT_SECONDS,
    )
    if not exited:
        raise BridgeError(1, "stop_failed", "bridge did not terminate before the deadline")
    if _read_pid_state() != state:
        raise BridgeError(1, "identity_mismatch", "bridge PID state changed during shutdown")
    try:
        (STATE_DIR / "bridge.pid").unlink()
    except OSError as error:
        raise BridgeError(1, "stop_failed", "bridge PID state could not be cleared") from error
    return state.pid


def status() -> int:
    """Return the PID only when persisted process and config identities match."""
    config_sha256 = load_network().config_sha256
    state = _read_pid_state()
    if not _owns_process(state, config_sha256):
        raise BridgeError(1, "not_running", "bridge is not running")
    return state.pid
