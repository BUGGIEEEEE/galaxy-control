#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed): brew install uv
# 2. Run: uv run galaxy_screen.py doctor|view|control|record|stop
# 3. Or make executable and run: chmod +x galaxy_screen.py && ./galaxy_screen.py doctor
# ──────────────────

"""Fixed-profile scrcpy CLI for one enrolled Galaxy."""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Sequence
from typing import assert_never

from galaxy_adb import AdbRuntime
from galaxy_process import JsonObject, error_envelope, run_command, success_envelope
from galaxy_profile import ProfileError, load_profile
from galaxy_screen_core import ScreenError, parse_request
from galaxy_screen_session import ScreenRuntime, doctor, start, stop


def execute(argv: Sequence[str], runtime: ScreenRuntime) -> tuple[JsonObject, int]:
    """Execute one exact screen profile."""
    action = argv[0] if argv else "unknown"
    try:
        request = parse_request(tuple(argv))
        match request.action:
            case "doctor":
                result = doctor(runtime)
            case "stop":
                result = stop()
            case "view" | "control" | "record":
                result = start(request, runtime)
            case unreachable:
                assert_never(unreachable)
    except ScreenError as error:
        return error_envelope(action, error.code, error.message), 1
    return success_envelope(action, result), 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the screen adapter."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        profile = load_profile()
    except ProfileError as error:
        envelope = error_envelope(args[0] if args else "unknown", error.code, error.message)
        exit_code = 1
    else:
        adb = AdbRuntime(profile, shutil.which("adb"), run_command, lambda: "")
        envelope, exit_code = execute(args, ScreenRuntime(adb, shutil.which("scrcpy"), run_command))
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
