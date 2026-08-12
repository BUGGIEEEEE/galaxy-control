#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run: uv run oneui_ledger.py check --manifest /ABS/manifest.tsv --ledger /ABS/ledger.tsv --progress /ABS/progress.tsv --selected-count N
# ──────────────────

"""Check One UI manifest, selection ledger, count, and progress evidence."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from galaxy_process import JsonObject, error_envelope, success_envelope

MAX_INPUT_BYTES: Final = 2_097_152
Status = Literal["completed", "pending", "held"]


@dataclass(frozen=True, slots=True)
class LedgerError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ManifestItem:
    item_id: str
    app_name: str
    target_folder: str
    identity_evidence: str


@dataclass(frozen=True, slots=True)
class ProgressItem:
    item_id: str
    app_name: str
    target_folder: str
    status: Status
    destination_present: bool
    source_absent: bool
    expected_count_ok: bool


def _rows(path: Path, fields: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise LedgerError("input_invalid", "ledger input must be a regular file")
    resolved = path.resolve()
    if resolved.stat().st_size > MAX_INPUT_BYTES:
        raise LedgerError("input_too_large", "ledger input exceeds the size limit")
    try:
        with resolved.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != fields:
                raise LedgerError("schema_invalid", "ledger input has an invalid schema")
            return tuple(dict(row) for row in reader)
    except OSError as error:
        raise LedgerError("input_invalid", "ledger input is unreadable") from error


def _manifest(path: Path) -> tuple[ManifestItem, ...]:
    fields = ("item_id", "app_name", "target_folder", "identity_evidence")
    rows = _rows(path, fields)
    items = tuple(ManifestItem(**row) for row in rows)
    if not items or len({item.item_id for item in items}) != len(items):
        raise LedgerError("manifest_invalid", "manifest item IDs must be unique")
    counts = Counter(item.app_name for item in items)
    for name, count in counts.items():
        if count <= 1:
            continue
        evidence = {item.identity_evidence for item in items if item.app_name == name}
        if "" in evidence or len(evidence) != count:
            raise LedgerError(
                "identity_unproven", "duplicate labels need distinct identity evidence"
            )
    return items


def _ledger(path: Path) -> tuple[tuple[int, ManifestItem], ...]:
    fields = ("selection_index", "item_id", "app_name", "target_folder", "identity_evidence")
    rows = _rows(path, fields)
    try:
        items = tuple(
            (
                int(row["selection_index"]),
                ManifestItem(
                    row["item_id"],
                    row["app_name"],
                    row["target_folder"],
                    row["identity_evidence"],
                ),
            )
            for row in rows
        )
    except ValueError as error:
        raise LedgerError("ledger_invalid", "selection indexes must be decimal integers") from error
    if tuple(index for index, _ in items) != tuple(range(1, len(items) + 1)):
        raise LedgerError("ledger_invalid", "selection indexes must be contiguous")
    return items


def _flag(value: str) -> bool:
    match value:
        case "true":
            return True
        case "false":
            return False
        case unreachable:
            raise LedgerError("progress_invalid", f"invalid proof flag: {unreachable}")


def _progress(path: Path) -> tuple[ProgressItem, ...]:
    fields = (
        "item_id",
        "app_name",
        "target_folder",
        "status",
        "destination_present",
        "source_absent",
        "expected_count_ok",
    )
    rows = _rows(path, fields)
    items: list[ProgressItem] = []
    for row in rows:
        match row["status"]:
            case "completed" | "pending" | "held" as status:
                items.append(
                    ProgressItem(
                        row["item_id"],
                        row["app_name"],
                        row["target_folder"],
                        status,
                        _flag(row["destination_present"]),
                        _flag(row["source_absent"]),
                        _flag(row["expected_count_ok"]),
                    )
                )
            case unreachable:
                raise LedgerError("progress_invalid", f"invalid progress status: {unreachable}")
    return tuple(items)


def check_ledger(
    manifest_path: Path,
    ledger_path: Path,
    progress_path: Path,
    selected_count: int,
) -> dict[str, int]:
    """Verify identity, quantity, and post-move proof as separate contracts."""
    manifest = _manifest(manifest_path)
    ledger = _ledger(ledger_path)
    progress = _progress(progress_path)
    if selected_count < 0 or selected_count != len(ledger):
        raise LedgerError("selection_count_mismatch", "selected count does not match ledger rows")
    manifest_by_id = {item.item_id: item for item in manifest}
    ledger_by_id = {item.item_id: item for _, item in ledger}
    if manifest_by_id != ledger_by_id:
        raise LedgerError(
            "ledger_identity_mismatch", "selection ledger identity differs from manifest"
        )
    progress_by_id = {item.item_id: item for item in progress}
    if len(progress_by_id) != len(progress) or set(progress_by_id) != set(manifest_by_id):
        raise LedgerError("progress_incomplete", "progress must record every manifest item once")
    for item in progress:
        expected = manifest_by_id[item.item_id]
        if (item.app_name, item.target_folder) != (expected.app_name, expected.target_folder):
            raise LedgerError(
                "progress_identity_mismatch", "progress identity differs from manifest"
            )
        if item.status == "completed" and not (
            item.destination_present and item.source_absent and item.expected_count_ok
        ):
            raise LedgerError("completion_unproven", "completed move requires all three proofs")
    statuses = Counter(item.status for item in progress)
    return {
        "manifest_count": len(manifest),
        "ledger_count": len(ledger),
        "selected_count": selected_count,
        "completed_count": statuses["completed"],
        "pending_count": statuses["pending"],
        "held_count": statuses["held"],
    }


def execute(argv: tuple[str, ...]) -> tuple[JsonObject, int]:
    """Execute the fixed local ledger-check profile."""
    action = argv[0] if argv else "unknown"
    try:
        match argv:
            case (
                "check",
                "--manifest",
                manifest_value,
                "--ledger",
                ledger_value,
                "--progress",
                progress_value,
                "--selected-count",
                selected_count_value,
            ):
                try:
                    selected_count = int(selected_count_value)
                except ValueError as error:
                    raise LedgerError(
                        "invalid_request",
                        "selected count must be a decimal integer",
                    ) from error
                checked = check_ledger(
                    Path(manifest_value),
                    Path(ledger_value),
                    Path(progress_value),
                    selected_count,
                )
            case _:
                raise LedgerError("invalid_request", "unsupported command or option order")
    except LedgerError as error:
        return error_envelope(action, error.code, error.message), 1
    result: JsonObject = dict(checked)
    return success_envelope(action, result), 0


def main(argv: tuple[str, ...] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    envelope, exit_code = execute(args)
    _ = sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
