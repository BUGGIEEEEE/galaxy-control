#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx2[http2,brotli,zstd]",
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Enroll one device: uv run galaxy_setup.py enroll --approved
# 2. Run: uv run galaxy_doctor.py
# ──────────────────

"""Read-only JSON doctor for every Galaxy Control path."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from galaxy_doctor_core import DoctorRuntime, PreflightTarget, inspect_device
from galaxy_process import JsonObject, error_envelope, run_command, success_envelope
from galaxy_profile import ProfileError, load_profile
from galaxy_setup import find_executable
from openminis_client import call_bridge


def execute(argv: Sequence[str], runtime: DoctorRuntime) -> tuple[JsonObject, int]:
    """Execute one fixed read-only preflight target."""
    match tuple(argv):
        case ():
            target = PreflightTarget.ALL
        case ("all" | "openminis" | "adb" | "scrcpy" as raw_target,):
            target = PreflightTarget(raw_target)
        case _:
            return error_envelope(
                "doctor",
                "invalid_request",
                "doctor accepts only all|openminis|adb|scrcpy",
            ), 1
    return success_envelope("doctor", inspect_device(runtime, target)), 0


def main(argv: Sequence[str] | None = None) -> int:
    """Print exactly one stable JSON envelope."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args not in {(), ("all",), ("openminis",), ("adb",), ("scrcpy",)}:
        envelope = error_envelope(
            "doctor",
            "invalid_request",
            "doctor accepts only all|openminis|adb|scrcpy",
        )
        exit_code = 1
    else:
        try:
            profile = load_profile()
        except ProfileError as error:
            envelope = error_envelope("doctor", error.code, error.message)
            exit_code = 1
        else:
            runtime = DoctorRuntime(profile, run_command, find_executable, call_bridge)
            envelope, exit_code = execute(args, runtime)
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
