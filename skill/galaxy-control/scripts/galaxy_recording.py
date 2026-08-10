"""Atomic scrcpy recording preparation and container validation."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from galaxy_process import JsonObject
from galaxy_screen_core import ScreenError

WORK_DIRECTORY_PREFIX: Final = ".galaxy-screen-recording-"


@dataclass(frozen=True, slots=True)
class RecordingPaths:
    output: Path
    work_directory: Path
    temp_path: Path


def prepare_recording(output: Path | None) -> RecordingPaths | None:
    """Create one private temporary recording destination beside the final path."""
    if output is None:
        return None
    if os.path.lexists(output):
        raise ScreenError("record_target_exists", "record output already exists")
    work_directory = Path(tempfile.mkdtemp(prefix=WORK_DIRECTORY_PREFIX, dir=output.parent))
    work_directory.chmod(0o700)
    return RecordingPaths(
        output, work_directory, work_directory / f"capture{output.suffix.lower()}"
    )


def cleanup_recording(paths: RecordingPaths | None) -> None:
    """Remove only an empty failed managed recording workspace."""
    if paths is None:
        return
    try:
        if paths.temp_path.exists() and paths.temp_path.stat().st_size == 0:
            paths.temp_path.unlink()
        paths.work_directory.rmdir()
    except OSError:
        return


def _integrity(path: Path) -> JsonObject:
    try:
        metadata = path.lstat()
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError as error:
        raise ScreenError(
            "scrcpy_record_failed", "recording file could not be inspected"
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise ScreenError("scrcpy_record_failed", "recording file is empty or not regular")
    suffix = path.suffix.lower()
    valid = (suffix == ".mp4" and len(header) >= 8 and header[4:8] == b"ftyp") or (
        suffix == ".mkv" and header.startswith(b"\x1aE\xdf\xa3")
    )
    if not valid:
        raise ScreenError("scrcpy_record_failed", "recording container header is invalid")
    return {
        "size_bytes": metadata.st_size,
        "container": suffix.removeprefix("."),
        "header_valid": True,
    }


def finalize_recording(paths: RecordingPaths) -> JsonObject:
    """Validate and atomically publish a new recording without overwriting."""
    integrity = _integrity(paths.temp_path)
    if os.path.lexists(paths.output):
        raise ScreenError("record_target_exists", "record output appeared during recording")
    try:
        os.link(paths.temp_path, paths.output, follow_symlinks=False)
    except FileExistsError as error:
        raise ScreenError("record_target_exists", "record output already exists") from error
    except OSError as error:
        raise ScreenError("scrcpy_record_failed", "recording could not be finalized") from error
    paths.temp_path.unlink()
    paths.work_directory.rmdir()
    return {"path": str(paths.output), **integrity}
