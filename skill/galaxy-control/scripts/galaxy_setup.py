#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed): brew install uv
# 2. Run: uv run galaxy_setup.py doctor|plan|enroll|apply|resume|verify|show-profile
# 3. Or make executable and run: chmod +x galaxy_setup.py && ./galaxy_setup.py plan
# ──────────────────

"""Resumable onboarding for the portable Galaxy Control skill."""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from galaxy_process import JsonObject, error_envelope, run_command, success_envelope
from galaxy_profile import ProfileError, load_profile, set_auto_reconnect_adb, set_steady_adb
from galaxy_setup_core import SetupError, SetupRuntime, apply_plan, build_plan, enroll

TAILSCALE_APP_CLI: Final = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")


def find_executable(name: str) -> str | None:
    """Resolve a PATH tool or the official macOS Tailscale app CLI."""
    found = shutil.which(name)
    if found is not None:
        return found
    if (
        name == "tailscale"
        and TAILSCALE_APP_CLI.is_file()
        and os.access(TAILSCALE_APP_CLI, os.X_OK)
    ):
        return str(TAILSCALE_APP_CLI)
    return None


def _plan_result(runtime: SetupRuntime) -> JsonObject:
    plan = build_plan(runtime)
    status = "READY" if not plan.install_commands and not plan.user_actions else "NEEDS_USER_ACTION"
    return {
        "status": status,
        "install_commands": [list(command) for command in plan.install_commands],
        "user_actions": list(plan.user_actions),
        "updates_existing_tools": False,
    }


def _doctor_result(runtime: SetupRuntime) -> JsonObject:
    result = _plan_result(runtime)
    try:
        profile = load_profile()
    except ProfileError as error:
        result["profile"] = {"enrolled": False, "error": error.code}
        result["status"] = "NEEDS_USER_ACTION"
    else:
        result["profile"] = {
            "enrolled": True,
            "expected_model": profile.expected_model,
            "steady_adb_enabled": profile.steady_adb_enabled,
            "auto_reconnect_adb_enabled": profile.auto_reconnect_adb_enabled,
        }
    result["computer_use"] = {"requires_live_permission_test": True}
    return result


def _show_profile() -> JsonObject:
    profile = load_profile()
    return {
        "enrolled": True,
        "expected_model": profile.expected_model,
        "openminis_port": profile.openminis_port,
        "steady_adb_enabled": profile.steady_adb_enabled,
        "auto_reconnect_adb_enabled": profile.auto_reconnect_adb_enabled,
        "device_identifiers_redacted": True,
    }


def execute(argv: Sequence[str], runtime: SetupRuntime) -> tuple[JsonObject, int]:
    """Execute one exact setup profile and return a stable JSON envelope."""
    action = argv[0] if argv else "unknown"
    result: JsonObject
    try:
        match tuple(argv):  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
            case ("doctor",) | ("resume",) | ("verify",):
                result = _doctor_result(runtime)
            case ("plan",):
                result = _plan_result(runtime)
            case ("show-profile",):
                result = _show_profile()
            case ("enroll", "--approved"):
                profile = enroll(runtime)
                result = {
                    "status": "ENROLLED",
                    "expected_model": profile.expected_model,
                    "device_identifiers_redacted": True,
                }
            case ("enroll", "--serial", selected_serial, "--approved"):
                profile = enroll(runtime, selected_serial)
                result = {
                    "status": "ENROLLED",
                    "expected_model": profile.expected_model,
                    "device_identifiers_redacted": True,
                }
            case ("enroll",) | ("enroll", "--serial", _) | ("apply",):
                raise SetupError("approval_required", "this setup action changes local state")
            case ("apply", "--approved"):
                plan = build_plan(runtime)
                applied = apply_plan(plan, runtime)
                result = {
                    "status": "NEEDS_USER_ACTION" if plan.user_actions else "READY",
                    "installed_count": applied,
                    "user_actions": list(plan.user_actions),
                }
            case ("enable-steady-adb",) | ("disable-steady-adb",):
                raise SetupError("approval_required", "this changes the fixed TCP ADB preference")
            case ("enable-steady-adb", "--approved"):
                profile = set_steady_adb(True)
                result = {
                    "steady_adb_enabled": profile.steady_adb_enabled,
                    "security_warning": "fixed TCP ADB may be reachable from the local LAN",
                }
            case ("disable-steady-adb", "--approved"):
                profile = set_steady_adb(False)
                result = {"steady_adb_enabled": profile.steady_adb_enabled}
            case ("enable-auto-reconnect",) | ("disable-auto-reconnect",):
                raise SetupError(
                    "approval_required",
                    "this changes the paired ADB reconnect preference",
                )
            case ("enable-auto-reconnect", "--approved"):
                profile = set_auto_reconnect_adb(True)
                result = {
                    "auto_reconnect_adb_enabled": profile.auto_reconnect_adb_enabled,
                }
            case ("disable-auto-reconnect", "--approved"):
                profile = set_auto_reconnect_adb(False)
                result = {
                    "auto_reconnect_adb_enabled": profile.auto_reconnect_adb_enabled,
                }
            case _:
                raise SetupError("invalid_request", "unsupported setup command or option")
    except (SetupError, ProfileError) as error:
        return error_envelope(action, error.code, error.message), 1
    return success_envelope(action, result), 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the setup CLI."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    envelope, exit_code = execute(args, SetupRuntime(run_command, find_executable))
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
