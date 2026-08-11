#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Keep this file, its lifecycle/process modules, and core directory together.
# 2. Run inside the OpenMinis Linux environment: python3 openminis_bridge_control.py status
# 3. Use only init-token, start, status, or stop; serve is an internal lifecycle command.
# ──────────────────

"""Fixed local lifecycle entrypoint for OpenMinis Control v2."""

from __future__ import annotations

import argparse
import sys
from enum import StrEnum
from typing import assert_never

from openminis_bridge_control_core import BridgeError, load_network, serve
from openminis_bridge_control_lifecycle import initialize_token, read_token, start, status, stop


class _Arguments(argparse.Namespace):
    command: str = ""
    config_sha256: str | None = None
    ready_fd: int | None = None
    launch_id: str | None = None


class _Command(StrEnum):
    INITIALIZE = "init-token"
    SERVE = "serve"
    START = "start"
    STOP = "stop"
    STATUS = "status"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenMinis Control v2 bridge")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_command = commands.add_parser(_Command.SERVE.value)
    _ = serve_command.add_argument("--config-sha256", required=True, help=argparse.SUPPRESS)
    _ = serve_command.add_argument("--ready-fd", type=int, help=argparse.SUPPRESS)
    _ = serve_command.add_argument("--launch-id", help=argparse.SUPPRESS)
    for name in (_Command.INITIALIZE, _Command.START, _Command.STOP, _Command.STATUS):
        _ = commands.add_parser(name.value)
    return parser


def _main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv, namespace=_Arguments())
    command = _Command(arguments.command)
    try:
        match command:
            case _Command.INITIALIZE:
                initialize_token()
                _ = sys.stdout.write("token initialized\n")
            case _Command.SERVE:
                if arguments.config_sha256 is None:
                    raise BridgeError(1, "invalid_config", "config identity is required")
                network = load_network(arguments.config_sha256)
                serve(network, read_token(), arguments.ready_fd)
            case _Command.START:
                _ = sys.stdout.write(f"started PID {start()}\n")
            case _Command.STOP:
                _ = sys.stdout.write(f"stopped PID {stop()}\n")
            case _Command.STATUS:
                _ = sys.stdout.write(f"running PID {status()}\n")
            case unreachable:
                assert_never(unreachable)
    except FileExistsError:
        _ = sys.stderr.write("error: token already exists\n")
        return 1
    except BridgeError as error:
        _ = sys.stderr.write(f"error:{error.code}:{error.message}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
