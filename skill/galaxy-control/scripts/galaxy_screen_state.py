"""Private owned-process identity state for managed scrcpy sessions."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from galaxy_screen_core import SESSION_PREFIX, ScreenError

STATE_DIRECTORY_ENV: Final = "GALAXY_SCREEN_STATE_DIR"
STATE_FILE_NAME: Final = "scrcpy-session.json"
MAX_STATE_BYTES: Final = 32_768


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    ps_start: str
    ps_command: str


class ScreenState(BaseModel):
    """Complete scrcpy process and output ownership proof."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    session_id: str = Field(pattern=r"^[A-Za-z0-9]{6,64}$")
    pid: Annotated[int, Field(gt=0)]
    profile: Literal["view", "control", "record"]
    serial: str
    model: str
    executable: str
    argv: tuple[str, ...]
    ps_start: str
    ps_command: str
    stderr_path: str
    output_path: str | None
    record_work_dir: str | None
    record_temp_path: str | None


def state_directory() -> Path:
    """Return a private cache directory outside the installed skill."""
    configured = os.environ.get(STATE_DIRECTORY_ENV)
    directory = (
        Path(configured)
        if configured is not None
        else Path.home() / "Library" / "Caches" / "galaxy-control" / "screen"
    )
    if not directory.is_absolute():
        raise ScreenError("state_unavailable", "screen state directory must be absolute")
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        directory.mkdir(mode=0o700, parents=True)
    else:
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ScreenError("state_unavailable", "screen state directory must be private")
    return directory


def state_path() -> Path:
    return state_directory() / STATE_FILE_NAME


def write_state(state: ScreenState) -> None:
    """Atomically write private process ownership state."""
    path = state_path()
    encoded = state.model_dump_json().encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".screen-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            _ = handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _ = temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_state() -> ScreenState | None:
    """Load state only from a private regular bounded file."""
    path = state_path()
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > MAX_STATE_BYTES
    ):
        raise ScreenError("process_identity_mismatch", "screen state is not trustworthy")
    try:
        return ScreenState.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ScreenError("process_identity_mismatch", "screen state is invalid") from error


def remove_state() -> None:
    """Remove only the exact managed state file."""
    state_path().unlink(missing_ok=True)


def identity_matches(state: ScreenState, identity: ProcessIdentity) -> bool:
    """Require exact process start, command, argv, serial, and session marker."""
    marker = f"--window-title={SESSION_PREFIX}{state.session_id}"
    return (
        identity.ps_start == state.ps_start
        and identity.ps_command == state.ps_command
        and state.argv[0] == state.executable
        and marker in state.argv
        and marker in identity.ps_command
        and state.serial in state.argv
    )
