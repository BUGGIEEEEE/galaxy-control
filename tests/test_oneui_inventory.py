from __future__ import annotations

from pathlib import Path

import pytest

from oneui_inventory import execute
from oneui_inventory_core import (
    InventoryError,
    PickerInventory,
    build_union,
    load_inventory,
    replay_picker,
)

FIXTURES = Path(__file__).parent / "fixtures" / "oneui"


def test_saved_picker_dump_replay_stitches_overlap_and_skips_partial_row() -> None:
    # Given / When
    inventory = replay_picker(FIXTURES / "picker-a.jsonl", "boot-a", "folder-a")

    # Then
    assert inventory.apps == ("Alpha", "Beta", "Twin", "Utility")


def test_saved_picker_dump_replay_refuses_selected_state() -> None:
    # Given / When / Then
    with pytest.raises(InventoryError, match="read-only"):
        _ = replay_picker(FIXTURES / "picker-selected.jsonl", "boot-a", "folder-a")


def test_union_uses_maximum_label_occurrence_across_same_session_pickers() -> None:
    # Given
    first = PickerInventory("boot-a", "folder-a", ("Alpha", "Twin", "Twin"))
    second = PickerInventory("boot-a", "folder-b", ("Alpha", "Folder App", "Twin"))

    # When
    union = build_union((first, second))

    # Then
    assert union.apps == ("Alpha", "Folder App", "Twin", "Twin")
    assert union.missing_by_source == {
        "folder-a": ("Folder App",),
        "folder-b": ("Twin",),
    }


def test_union_refuses_different_capture_sessions() -> None:
    # Given
    first = PickerInventory("boot-a", "folder-a", ("Alpha",))
    second = PickerInventory("boot-b", "folder-b", ("Beta",))

    # When / Then
    with pytest.raises(InventoryError, match="same capture session"):
        _ = build_union((first, second))


def test_union_requires_more_than_one_distinct_picker() -> None:
    # Given
    inventory = PickerInventory("boot-a", "folder-a", ("Alpha",))

    # When / Then
    with pytest.raises(InventoryError, match="two distinct"):
        _ = build_union((inventory,))


def test_replay_cli_writes_stable_read_only_envelope_and_artifacts(tmp_path: Path) -> None:
    # Given
    output = tmp_path / "replayed"

    # When
    envelope, exit_code = execute(
        (
            "replay",
            "--input",
            str(FIXTURES / "picker-a.jsonl"),
            "--output",
            str(output),
            "--capture-session",
            "boot-a",
            "--source",
            "folder-a",
        )
    )

    # Then
    assert exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"] == {
        "status": "REPLAYED",
        "row_count": 4,
        "selection_actions": 0,
        "phone_commands": 0,
    }
    assert (output / "app_selector_inventory.tsv").is_file()
    assert (output / "inventory_summary.json").is_file()


def test_inventory_cli_rejects_arbitrary_option_without_writing(tmp_path: Path) -> None:
    # Given
    output = tmp_path / "replayed"

    # When
    envelope, exit_code = execute(
        (
            "replay",
            "--input",
            str(FIXTURES / "picker-a.jsonl"),
            "--output",
            str(output),
            "--capture-session",
            "boot-a",
            "--host",
            "example.invalid",
        )
    )

    # Then
    assert exit_code == 1
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_request"
    assert not output.exists()


def test_replay_refuses_symlinked_input(tmp_path: Path) -> None:
    # Given
    link = tmp_path / "picker-link.jsonl"
    link.symlink_to(FIXTURES / "picker-a.jsonl")

    # When / Then
    with pytest.raises(InventoryError, match="regular file"):
        _ = replay_picker(link, "boot-a", "folder-a")


def test_union_input_refuses_tampered_sequence(tmp_path: Path) -> None:
    # Given
    inventory = tmp_path / "inventory.tsv"
    _ = inventory.write_text(
        """capture_session\tsource\tsequence_no\tapp_name\tlabel_occurrence
boot-a\tfolder-a\t1\tAlpha\t1
boot-a\tfolder-a\t3\tBeta\t1
""",
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(InventoryError, match="sequence or occurrence"):
        _ = load_inventory(inventory)
