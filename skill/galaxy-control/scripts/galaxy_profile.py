"""Strict private device profile for the portable Galaxy Control skill."""

from __future__ import annotations

import ipaddress
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

PROFILE_HOME_ENV: Final = "GALAXY_CONTROL_HOME"
PROFILE_FILE_NAME: Final = "device.json"
MAX_PROFILE_BYTES: Final = 8192
TAILNET: Final = ipaddress.IPv4Network("100.64.0.0/10")


@dataclass(frozen=True, slots=True)
class ProfileError(Exception):
    """Profile trust or parsing failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class DeviceProfile(BaseModel):
    """Validated identity and fixed endpoints for exactly one enrolled Galaxy."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    schema_version: Literal[1] = Field(alias="schema", serialization_alias="schema")
    physical_serial: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    expected_model: Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9_]{1,63}$")]
    tailscale_ipv4: str
    openminis_port: Annotated[int, Field(ge=1, le=65535)] = 43129
    steady_adb_enabled: bool = False
    auto_reconnect_adb_enabled: bool = False
    steady_adb_port: Literal[5555] = 5555

    @field_validator("tailscale_ipv4")
    @classmethod
    def parse_tailnet_address(cls, raw: str) -> str:
        """Accept only a literal Tailscale IPv4 address."""
        try:
            address = ipaddress.IPv4Address(raw)
        except ipaddress.AddressValueError as error:
            raise PydanticCustomError(
                "tailscale_ipv4", "tailscale_ipv4 must be a literal IPv4 address"
            ) from error
        if address not in TAILNET:
            raise PydanticCustomError(
                "tailscale_ipv4", "tailscale_ipv4 must be inside 100.64.0.0/10"
            )
        return str(address)

    @property
    def openminis_origin(self) -> str:
        """Return the exact enrolled OpenMinis origin."""
        return f"http://{self.tailscale_ipv4}:{self.openminis_port}"

    @property
    def steady_endpoint(self) -> str:
        """Return the optional fixed TCP ADB endpoint."""
        return f"{self.tailscale_ipv4}:{self.steady_adb_port}"


def profile_directory() -> Path:
    """Return the absolute per-user application-support directory."""
    configured = os.environ.get(PROFILE_HOME_ENV)
    directory = (
        Path(configured)
        if configured is not None
        else Path.home() / "Library" / "Application Support" / "galaxy-control"
    )
    if not directory.is_absolute():
        raise ProfileError("profile_unavailable", "profile directory must be absolute")
    return directory


def profile_path() -> Path:
    """Return the exact private device profile path."""
    return profile_directory() / PROFILE_FILE_NAME


def _require_private_directory(directory: Path, *, create: bool) -> None:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        if not create:
            raise ProfileError("profile_missing", "device profile is not enrolled") from None
        directory.mkdir(mode=0o700, parents=True)
        return
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ProfileError("profile_unavailable", "profile directory must be private")


def write_profile(profile: DeviceProfile) -> Path:
    """Atomically write one validated private profile."""
    directory = profile_directory()
    _require_private_directory(directory, create=True)
    encoded = profile.model_dump_json(by_alias=True).encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".device-", dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            _ = handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _ = temporary.replace(profile_path())
    finally:
        temporary.unlink(missing_ok=True)
    return profile_path()


def load_profile() -> DeviceProfile:
    """Read and parse a trustworthy private profile."""
    directory = profile_directory()
    _require_private_directory(directory, create=False)
    path = profile_path()
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise ProfileError("profile_missing", "device profile is not enrolled") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > MAX_PROFILE_BYTES
    ):
        raise ProfileError("profile_unavailable", "profile must be a private regular file")
    try:
        return DeviceProfile.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ProfileError("profile_invalid", "device profile is invalid") from error


def set_steady_adb(enabled: bool) -> DeviceProfile:
    """Persist the user's explicit fixed TCP ADB preference."""
    updated = load_profile().model_copy(update={"steady_adb_enabled": enabled})
    _ = write_profile(updated)
    return updated


def set_auto_reconnect_adb(enabled: bool) -> DeviceProfile:
    """Persist the user's explicit paired ADB reconnect preference."""
    updated = load_profile().model_copy(update={"auto_reconnect_adb_enabled": enabled})
    _ = write_profile(updated)
    return updated
