"""Private boot-scoped state for official Wireless Debugging."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Annotated, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from galaxy_adb import AdbError
from galaxy_profile import DeviceProfile

STATE_DIRECTORY_ENV: Final = "GALAXY_WIRELESS_STATE_DIR"
STATE_FILE_NAME: Final = "wireless-session.json"
MAX_STATE_BYTES: Final = 4096


class WirelessState(BaseModel):
    """Validated cache that binds a dynamic endpoint to one profile and boot."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    endpoint: str = Field(pattern=r"^100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}:[0-9]{1,5}$")
    port: Annotated[int, Field(ge=1, le=65535)]
    boot_session_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def profile_hash(profile: DeviceProfile) -> str:
    """Hash enrolled identity for cache invalidation without storing raw fields."""
    material = f"{profile.physical_serial}\0{profile.expected_model}\0{profile.tailscale_ipv4}"
    return hashlib.sha256(material.encode()).hexdigest()


def state_directory() -> Path:
    """Return the absolute private wireless cache directory."""
    configured = os.environ.get(STATE_DIRECTORY_ENV)
    directory = (
        Path(configured)
        if configured is not None
        else Path.home() / "Library" / "Caches" / "galaxy-control"
    )
    if not directory.is_absolute():
        raise AdbError("state_unavailable", "wireless state directory must be absolute")
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        directory.mkdir(mode=0o700, parents=True)
    else:
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise AdbError("state_unavailable", "wireless state directory must be private")
    return directory


def state_path() -> Path:
    return state_directory() / STATE_FILE_NAME


def write_state(state: WirelessState) -> None:
    """Atomically write private validated wireless state."""
    path = state_path()
    encoded = state.model_dump_json().encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".wireless-", dir=path.parent)
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


def load_state(profile: DeviceProfile) -> WirelessState | None:
    """Load state only when its file and enrolled profile binding are trustworthy."""
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
        raise AdbError("state_invalid", "wireless state is not trustworthy")
    try:
        state = WirelessState.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise AdbError("state_invalid", "wireless state is invalid") from error
    if state.profile_hash != profile_hash(profile):
        raise AdbError("state_profile_mismatch", "wireless state belongs to another profile")
    return state
