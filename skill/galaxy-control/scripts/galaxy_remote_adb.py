#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed): brew install uv
# 2. Run: uv run galaxy_remote_adb.py doctor
# 3. Or make executable and run: chmod +x galaxy_remote_adb.py && ./galaxy_remote_adb.py doctor
# ──────────────────

"""Fixed-profile ADB adapter for one enrolled Galaxy."""

from __future__ import annotations

import getpass
import json
import shutil
import sys
from collections.abc import Sequence

from galaxy_adb import AdbRuntime
from galaxy_process import JsonObject, error_envelope, run_command
from galaxy_profile import ProfileError, load_profile
from galaxy_remote_adb_core import execute_legacy
from galaxy_remote_adb_wireless import execute_wireless

__all__ = ["AdbRuntime", "execute"]


def execute(argv: Sequence[str], runtime: AdbRuntime) -> tuple[JsonObject, int]:
    """Route exact wireless and fixed ADB profiles."""
    if argv and (argv[0].startswith("wireless-") or argv[0] == "legacy-enable-from-wireless"):
        return execute_wireless(argv, runtime)
    return execute_legacy(argv, runtime)


def _read_pair_code() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("Galaxy pairing code: ")
    return sys.stdin.readline(64)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ADB adapter."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        runtime = AdbRuntime(load_profile(), shutil.which("adb"), run_command, _read_pair_code)
    except ProfileError as error:
        envelope = error_envelope(args[0] if args else "unknown", error.code, error.message)
        exit_code = 1
    else:
        envelope, exit_code = execute(args, runtime)
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
