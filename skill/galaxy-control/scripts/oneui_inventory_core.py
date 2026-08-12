"""Replay saved One UI picker dumps and build same-session inventory unions."""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, ValidationError

MAX_INPUT_BYTES: Final = 33_554_432
MAX_WINDOWS: Final = 512
SAFE_ID: Final = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
SELECTED_COUNT: Final = re.compile(r"\d+개 선택됨")


@dataclass(frozen=True, slots=True)
class InventoryError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class Point(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    x: int
    y: int


class PickerNode(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    text: str | None = None
    contentDesc: str | None = None  # noqa: N815 -- OpenMinis wire field.
    clickable: bool = False
    center: Point


class DumpData(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    nodes: tuple[PickerNode, ...]


class DumpResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    data: DumpData


class DumpEnvelope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    ok: bool
    result: DumpResult


class ReplayRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")
    step: int
    labels: tuple[str, ...] | None = None
    ui_dump: DumpEnvelope


@dataclass(frozen=True, slots=True)
class PickerInventory:
    capture_session: str
    source: str
    apps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnionInventory:
    capture_session: str
    apps: tuple[str, ...]
    missing_by_source: dict[str, tuple[str, ...]]


def _checked_identifier(value: str, label: str) -> str:
    if SAFE_ID.fullmatch(value) is None:
        raise InventoryError("invalid_identifier", f"{label} is not a safe identifier")
    return value


def _checked_path(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise InventoryError("input_invalid", "picker replay input must be a regular file")
    resolved = path.resolve()
    if resolved.stat().st_size > MAX_INPUT_BYTES:
        raise InventoryError("input_too_large", "picker replay input exceeds the size limit")
    return resolved


def _extract_labels(record: ReplayRecord) -> tuple[str, ...]:
    if not record.ui_dump.ok:
        raise InventoryError("dump_unsuccessful", "saved ui-dump was not successful")
    nodes = record.ui_dump.result.data.nodes
    done = any(node.text == "완료" and node.clickable for node in nodes)
    search = any(node.contentDesc == "검색" and node.clickable for node in nodes)
    picker = any(node.text == "앱 선택" for node in nodes)
    headers = tuple(node for node in nodes if node.text == "모든 앱")
    if not done or not search or not picker or len(headers) != 1:
        raise InventoryError("picker_guard_failed", "saved dump is not a stable app picker")
    if any(node.text is not None and SELECTED_COUNT.fullmatch(node.text) for node in nodes):
        raise InventoryError("picker_not_read_only", "picker replay must be read-only")

    header_y = headers[0].center.y
    row_centers = sorted(
        {
            node.center.y
            for node in nodes
            if node.clickable
            and node.center.y > header_y
            and node.text != "완료"
            and node.contentDesc not in {"검색", "뒤로가기", "홈", "최근 앱", "접근성"}
        }
    )
    labels: list[str] = []
    for row_y in row_centers:
        candidates = tuple(
            node.text.strip()
            for node in nodes
            if not node.clickable
            and node.text is not None
            and node.text.strip()
            and abs(node.center.y - row_y) <= 3
            and node.center.y > header_y
        )
        if not candidates:
            continue
        if len(candidates) != 1 or any("\t" in item or "\n" in item for item in candidates):
            raise InventoryError("picker_row_ambiguous", "picker row identity is ambiguous")
        labels.append(candidates[0])
    if not labels:
        raise InventoryError("picker_empty", "saved picker dump contains no complete app row")
    return tuple(labels)


def _overlap_length(existing: tuple[str, ...], window: tuple[str, ...]) -> int:
    for size in range(min(len(existing), len(window)), 0, -1):
        if existing[-size:] == window[:size]:
            return size
    return 0


def replay_picker(path: Path, capture_session: str, source: str) -> PickerInventory:
    """Replay saved dumps without issuing any phone action."""
    checked_session = _checked_identifier(capture_session, "capture session")
    checked_source = _checked_identifier(source, "source")
    windows: list[tuple[str, ...]] = []
    try:
        with _checked_path(path).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number > MAX_WINDOWS:
                    raise InventoryError("too_many_windows", "picker replay has too many windows")
                record = ReplayRecord.model_validate_json(line)
                labels = _extract_labels(record)
                if record.labels is not None and record.labels != labels:
                    raise InventoryError(
                        "label_replay_mismatch", "stored labels do not match ui-dump"
                    )
                windows.append(labels)
    except (OSError, ValidationError) as error:
        raise InventoryError("input_invalid", "picker replay input is invalid") from error
    if not windows:
        raise InventoryError("picker_empty", "picker replay contains no windows")

    sequence = windows[0]
    for window in windows[1:]:
        if window == sequence[-len(window) :]:
            continue
        overlap = _overlap_length(sequence, window)
        if overlap == 0:
            raise InventoryError("inventory_discontinuity", "picker windows have no overlap")
        sequence += window[overlap:]
    return PickerInventory(checked_session, checked_source, sequence)


def build_union(inventories: tuple[PickerInventory, ...]) -> UnionInventory:
    """Build maximum-occurrence union across distinct same-session pickers."""
    sources = {inventory.source for inventory in inventories}
    sessions = {inventory.capture_session for inventory in inventories}
    if len(inventories) < 2 or len(sources) != len(inventories):
        raise InventoryError("insufficient_sources", "two distinct picker sources are required")
    if len(sessions) != 1:
        raise InventoryError(
            "session_mismatch", "picker sources must share the same capture session"
        )
    counters: dict[str, Counter[str]] = {item.source: Counter(item.apps) for item in inventories}
    labels: set[str] = set()
    for counter in counters.values():
        labels.update(counter)
    maximum: Counter[str] = Counter(
        {label: max(counter[label] for counter in counters.values()) for label in labels}
    )
    apps = tuple(
        label for label in sorted(maximum, key=str.casefold) for _ in range(maximum[label])
    )
    missing = {
        source: tuple(
            label
            for label in sorted(maximum, key=str.casefold)
            for _ in range(maximum[label] - counter[label])
        )
        for source, counter in counters.items()
    }
    return UnionInventory(next(iter(sessions)), apps, missing)


def load_inventory(path: Path) -> PickerInventory:
    """Load one replay-produced inventory TSV."""
    try:
        with _checked_path(path).open(encoding="utf-8", newline="") as handle:
            rows = tuple(csv.DictReader(handle, delimiter="\t"))
    except OSError as error:
        raise InventoryError("input_invalid", "inventory TSV is unreadable") from error
    required = {"capture_session", "source", "sequence_no", "app_name", "label_occurrence"}
    if not rows or set(rows[0]) != required:
        raise InventoryError("input_invalid", "inventory TSV has an invalid schema")
    sessions = {row["capture_session"] for row in rows}
    sources = {row["source"] for row in rows}
    if len(sessions) != 1 or len(sources) != 1:
        raise InventoryError("input_invalid", "inventory TSV has mixed identity fields")
    session = _checked_identifier(next(iter(sessions)), "capture session")
    source = _checked_identifier(next(iter(sources)), "source")
    seen: Counter[str] = Counter()
    apps: list[str] = []
    for index, row in enumerate(rows, start=1):
        name = row["app_name"]
        seen[name] += 1
        if (
            not name.strip()
            or name != name.strip()
            or row["sequence_no"] != str(index)
            or row["label_occurrence"] != str(seen[name])
        ):
            raise InventoryError("input_invalid", "inventory TSV sequence or occurrence is invalid")
        apps.append(name)
    return PickerInventory(session, source, tuple(apps))
