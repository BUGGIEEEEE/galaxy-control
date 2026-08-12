#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Replay: uv run oneui_inventory.py replay --input /ABS/dumps.jsonl --output /ABS/new-dir --capture-session ID --source NAME
# 2. Union: uv run oneui_inventory.py union --input /ABS/a.tsv --input /ABS/b.tsv --output /ABS/new-dir
# ──────────────────

"""Read-only saved-dump replay and same-session One UI inventory union CLI."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Final

from galaxy_process import JsonObject, error_envelope, success_envelope
from oneui_inventory_core import (
    InventoryError,
    PickerInventory,
    UnionInventory,
    build_union,
    load_inventory,
    replay_picker,
)

OUTPUT_FILES: Final = ("app_selector_inventory.tsv", "inventory_summary.json")


def _new_output(path: str) -> Path:
    output = Path(path)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise InventoryError("output_invalid", "output must be a new absolute directory")
    try:
        output.mkdir(mode=0o700, parents=False)
    except OSError as error:
        raise InventoryError("output_invalid", "output directory could not be created") from error
    return output


def _write_inventory(output: Path, inventory: PickerInventory) -> None:
    path = output / OUTPUT_FILES[0]
    seen: Counter[str] = Counter()
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerows(
            (("capture_session", "source", "sequence_no", "app_name", "label_occurrence"),)
        )
        for index, name in enumerate(inventory.apps, start=1):
            seen[name] += 1
            writer.writerows(
                ((inventory.capture_session, inventory.source, index, name, seen[name]),)
            )
    summary = {
        "capture_session": inventory.capture_session,
        "source": inventory.source,
        "row_count": len(inventory.apps),
        "unique_label_count": len(seen),
        "selection_actions": 0,
        "complete_button_actions": 0,
    }
    _ = (output / OUTPUT_FILES[1]).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_union(output: Path, union: UnionInventory) -> None:
    inventory = PickerInventory(union.capture_session, "same-session-union", union.apps)
    path = output / OUTPUT_FILES[0]
    seen: Counter[str] = Counter()
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerows(
            (("capture_session", "source", "sequence_no", "app_name", "label_occurrence"),)
        )
        for index, name in enumerate(inventory.apps, start=1):
            seen[name] += 1
            writer.writerows(
                ((inventory.capture_session, inventory.source, index, name, seen[name]),)
            )
    summary = {
        "capture_session": inventory.capture_session,
        "source": inventory.source,
        "row_count": len(inventory.apps),
        "unique_label_count": len(seen),
        "source_count": len(union.missing_by_source),
        "missing_occurrence_count_by_source": {
            source: len(labels) for source, labels in union.missing_by_source.items()
        },
        "selection_actions": 0,
        "complete_button_actions": 0,
    }
    _ = (output / OUTPUT_FILES[1]).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _union_arguments(argv: tuple[str, ...]) -> tuple[tuple[Path, ...], str]:
    inputs: list[Path] = []
    output: str | None = None
    index = 0
    while index < len(argv):
        if index + 1 >= len(argv):
            raise InventoryError("invalid_request", "union arguments must be option-value pairs")
        option, value = argv[index : index + 2]
        match option:
            case "--input":
                inputs.append(Path(value))
            case "--output":
                if output is not None:
                    raise InventoryError("invalid_request", "union output may be specified once")
                output = value
            case unreachable:
                raise InventoryError("invalid_request", f"unsupported option: {unreachable}")
        index += 2
    if output is None or len(inputs) < 2:
        raise InventoryError("invalid_request", "union needs two inputs and one output")
    return tuple(inputs), output


def execute(argv: tuple[str, ...]) -> tuple[JsonObject, int]:
    """Execute one local read-only artifact profile."""
    action = argv[0] if argv else "unknown"
    try:
        match argv:
            case (
                "replay",
                "--input",
                input_value,
                "--output",
                output_value,
                "--capture-session",
                capture_session,
                "--source",
                source,
            ):
                inventory = replay_picker(
                    Path(input_value),
                    capture_session,
                    source,
                )
                output = _new_output(output_value)
                _write_inventory(output, inventory)
                result: JsonObject = {
                    "status": "REPLAYED",
                    "row_count": len(inventory.apps),
                    "selection_actions": 0,
                    "phone_commands": 0,
                }
            case ("union", *tail):
                input_paths, output_value = _union_arguments(tuple(tail))
                inputs = tuple(load_inventory(value) for value in input_paths)
                combined = build_union(inputs)
                output = _new_output(output_value)
                _write_union(output, combined)
                result = {
                    "status": "UNION_VERIFIED",
                    "source_count": len(inputs),
                    "row_count": len(combined.apps),
                    "selection_actions": 0,
                    "phone_commands": 0,
                }
            case _:
                raise InventoryError("invalid_request", "unsupported command or option order")
    except InventoryError as error:
        return error_envelope(action, error.code, error.message), 1
    return success_envelope(action, result), 0


def main(argv: tuple[str, ...] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    envelope, exit_code = execute(args)
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
