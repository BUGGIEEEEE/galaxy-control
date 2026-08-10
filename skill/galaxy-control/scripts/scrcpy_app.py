"""Materialize a private macOS app identity around an installed scrcpy binary."""

from __future__ import annotations

import os
import plistlib
import stat
import tempfile
from pathlib import Path
from typing import Final

APP_BUNDLE_NAME: Final = "Galaxy Control Scrcpy.app"
APP_BUNDLE_IDENTIFIER: Final = "io.github.galaxycontrol.scrcpy"
APP_DISPLAY_NAME: Final = "Galaxy Control Scrcpy"
INFO_PLIST: Final = plistlib.dumps(
    {
        "CFBundleExecutable": "scrcpy",
        "CFBundleIdentifier": APP_BUNDLE_IDENTIFIER,
        "CFBundleName": APP_DISPLAY_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
    },
    fmt=plistlib.FMT_XML,
    sort_keys=True,
)


def ensure_app_executable(scrcpy_path: str, runtime_directory: Path) -> str:
    """Return scrcpy through a private app bundle that Computer Use can address."""
    source = Path(scrcpy_path)
    if not source.is_absolute():
        raise OSError("scrcpy executable path must be absolute")
    metadata = source.stat()
    if not stat.S_ISREG(metadata.st_mode) or not os.access(source, os.X_OK):
        raise OSError("scrcpy executable is unavailable")
    bundle = runtime_directory / APP_BUNDLE_NAME
    contents = bundle / "Contents"
    macos = contents / "MacOS"
    for directory in (bundle, contents, macos):
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    info_path = contents / "Info.plist"
    try:
        current = info_path.read_bytes() == INFO_PLIST
    except FileNotFoundError:
        current = False
    if not current:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".Info-", dir=contents)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                _ = handle.write(INFO_PLIST)
                handle.flush()
                os.fsync(handle.fileno())
            _ = temporary.replace(info_path)
        finally:
            temporary.unlink(missing_ok=True)
    executable = macos / "scrcpy"
    if not executable.is_symlink() or executable.readlink() != source:
        temporary_link = macos / f".scrcpy-{os.getpid()}"
        temporary_link.unlink(missing_ok=True)
        temporary_link.symlink_to(source)
        _ = temporary_link.replace(executable)
    return str(executable)
