from __future__ import annotations

from pathlib import Path

from install_skill import InstallError, install


def test_installer_copies_skill_to_new_exact_destination(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source" / "skill" / "galaxy-control"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: galaxy-control\n---\n")
    destination = tmp_path / "codex" / "skills" / "galaxy-control"

    # When
    installed = install(source, destination)

    # Then
    assert installed == destination
    assert (destination / "SKILL.md").is_file()


def test_installer_refuses_to_overwrite_existing_skill(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("source")
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "SKILL.md").write_text("keep")

    # When
    try:
        install(source, destination)
    except InstallError as error:
        captured = error
    else:
        raise AssertionError("existing installation was overwritten")

    # Then
    assert captured.code == "destination_exists"
    assert (destination / "SKILL.md").read_text() == "keep"


def test_installer_requires_real_skill_manifest(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source"
    source.mkdir()

    # When
    try:
        install(source, tmp_path / "destination")
    except InstallError as error:
        captured = error
    else:
        raise AssertionError("invalid source was installed")

    # Then
    assert captured.code == "source_invalid"
