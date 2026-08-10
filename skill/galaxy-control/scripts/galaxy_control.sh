#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
UV=$(command -v uv || true)

if [ "$#" -eq 0 ]; then
    printf '%s\n' 'usage: galaxy_control.sh COMMAND [ARGUMENTS...]' >&2
    exit 64
fi

if [ -z "$UV" ]; then
    printf '%s\n' 'error:uv_not_installed:uv is unavailable' >&2
    exit 69
fi

exec "$UV" run --script "$SCRIPT_DIR/openminis_client.py" "$@"
