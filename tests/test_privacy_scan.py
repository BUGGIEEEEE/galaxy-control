from __future__ import annotations

from pathlib import Path

from privacy_scan import scan_files


def test_privacy_scan_rejects_absolute_macos_home_path(tmp_path: Path) -> None:
    # Given
    private = tmp_path / "leak.txt"
    private.write_text("runtime=/" + "Users/example/.codex/skills")

    # When
    findings = scan_files((private,))

    # Then
    assert len(findings) == 1
    assert findings[0].rule == "absolute_macos_home"


def test_privacy_scan_rejects_literal_pairing_code(tmp_path: Path) -> None:
    # Given
    private = tmp_path / "leak.txt"
    private.write_text('pairing_code="' + "123456" + '"')

    # When
    findings = scan_files((private,))

    # Then
    assert len(findings) == 1
    assert findings[0].rule == "literal_pairing_code"


def test_privacy_scan_allows_templates_and_fake_test_identity(tmp_path: Path) -> None:
    # Given
    safe = tmp_path / "safe.txt"
    safe.write_text(
        "<PRIVATE_SKILL_PATH>\n"
        "pairing code must contain six digits\n"
        "DEMO123456 SM_S921B 100.64.1.20\n"
    )

    # When / Then
    assert scan_files((safe,)) == ()
