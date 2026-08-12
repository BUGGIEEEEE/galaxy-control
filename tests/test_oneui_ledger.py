from __future__ import annotations

from pathlib import Path

import pytest

from oneui_ledger import LedgerError, check_ledger, execute

FIXTURES = Path(__file__).parent / "fixtures" / "oneui"


def test_manifest_ledger_and_progress_are_consistent() -> None:
    # Given / When
    result = check_ledger(
        FIXTURES / "manifest.tsv",
        FIXTURES / "ledger.tsv",
        FIXTURES / "progress.tsv",
        selected_count=3,
    )

    # Then
    assert result == {
        "manifest_count": 3,
        "ledger_count": 3,
        "selected_count": 3,
        "completed_count": 2,
        "pending_count": 1,
        "held_count": 0,
    }


def test_matching_selected_count_does_not_hide_wrong_app_identity(tmp_path: Path) -> None:
    # Given
    ledger = tmp_path / "ledger.tsv"
    _ = ledger.write_text(
        """selection_index\titem_id\tapp_name\ttarget_folder\tidentity_evidence
1\talpha\tWrong App\tTools\t
2\ttwin-a\tTwin\tGames\tpackage:example.twin.a
3\ttwin-b\tTwin\tTools\tpackage:example.twin.b
""",
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(LedgerError, match="identity"):
        _ = check_ledger(
            FIXTURES / "manifest.tsv",
            ledger,
            FIXTURES / "progress.tsv",
            selected_count=3,
        )


def test_duplicate_labels_require_distinct_identity_evidence(tmp_path: Path) -> None:
    # Given
    manifest = tmp_path / "manifest.tsv"
    _ = manifest.write_text(
        """item_id\tapp_name\ttarget_folder\tidentity_evidence
one\tTwin\tGames\t
two\tTwin\tTools\t
""",
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(LedgerError, match="identity evidence"):
        _ = check_ledger(manifest, FIXTURES / "ledger.tsv", FIXTURES / "progress.tsv", 3)


def test_completed_progress_requires_destination_source_and_count_proof(tmp_path: Path) -> None:
    # Given
    progress = tmp_path / "progress.tsv"
    _ = progress.write_text(
        (FIXTURES / "progress.tsv")
        .read_text(encoding="utf-8")
        .replace("completed\ttrue\ttrue\ttrue", "completed\ttrue\tfalse\ttrue", 1),
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(LedgerError, match="three proofs"):
        _ = check_ledger(
            FIXTURES / "manifest.tsv",
            FIXTURES / "ledger.tsv",
            progress,
            selected_count=3,
        )


def test_ledger_cli_returns_stable_success_envelope() -> None:
    # Given / When
    envelope, exit_code = execute(
        (
            "check",
            "--manifest",
            str(FIXTURES / "manifest.tsv"),
            "--ledger",
            str(FIXTURES / "ledger.tsv"),
            "--progress",
            str(FIXTURES / "progress.tsv"),
            "--selected-count",
            "3",
        )
    )

    # Then
    assert exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["ledger_count"] == 3
    assert envelope["result"]["selected_count"] == 3


def test_ledger_cli_returns_exact_error_for_bad_count() -> None:
    # Given / When
    envelope, exit_code = execute(
        (
            "check",
            "--manifest",
            str(FIXTURES / "manifest.tsv"),
            "--ledger",
            str(FIXTURES / "ledger.tsv"),
            "--progress",
            str(FIXTURES / "progress.tsv"),
            "--selected-count",
            "2",
        )
    )

    # Then
    assert exit_code == 1
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "selection_count_mismatch"


def test_ledger_refuses_symlinked_input(tmp_path: Path) -> None:
    # Given
    manifest = tmp_path / "manifest-link.tsv"
    manifest.symlink_to(FIXTURES / "manifest.tsv")

    # When / Then
    with pytest.raises(LedgerError, match="regular file"):
        _ = check_ledger(
            manifest,
            FIXTURES / "ledger.tsv",
            FIXTURES / "progress.tsv",
            selected_count=3,
        )
