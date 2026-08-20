from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import install_skill
from install_skill import InstallError, install, main, upgrade

if TYPE_CHECKING:
    import pytest


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


def test_upgrader_atomically_replaces_skill_and_retains_private_backup(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("new")
    (source / "VERSION").write_text("0.5.0\n")
    destination = tmp_path / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")

    # When
    upgraded = upgrade(source, destination)

    # Then
    assert upgraded.installed == destination
    assert upgraded.backup.parent == destination.parent / ".galaxy-control-backups"
    assert (destination / "SKILL.md").read_text() == "new"
    assert (destination / "VERSION").read_text().strip() == "0.5.0"
    assert (upgraded.backup / "SKILL.md").read_text() == "old"
    assert upgraded.backup.stat().st_mode & 0o777 == 0o700


def test_upgrader_refuses_symlink_destination(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("new")
    real_destination = tmp_path / "real"
    real_destination.mkdir()
    destination = tmp_path / "galaxy-control"
    destination.symlink_to(real_destination)

    # When
    try:
        upgrade(source, destination)
    except InstallError as error:
        captured = error
    else:
        raise AssertionError("symlink installation was upgraded")

    # Then
    assert captured.code == "destination_invalid"
    assert destination.is_symlink()


def test_upgrader_restores_previous_skill_when_activation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("new")
    destination = tmp_path / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    monkeypatch.setattr(
        install_skill,
        "_atomic_swap",
        lambda _staged, _destination: (_ for _ in ()).throw(
            OSError("simulated activation failure")
        ),
    )

    # When
    try:
        upgrade(source, destination)
    except InstallError as error:
        captured = error
    else:
        raise AssertionError("failed activation was reported as upgraded")

    # Then
    assert captured.code == "upgrade_failed"
    assert (destination / "SKILL.md").read_text() == "old"


def test_upgrade_cli_activates_bundled_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 0
    assert '"action":"upgrade"' in capsys.readouterr().out
    assert (destination / "VERSION").read_text().strip() == "0.5.1"


def test_upgrade_cli_secures_legacy_cache_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    cache_root = tmp_path / "Library" / "Caches" / "galaxy-control"
    screen_cache = cache_root / "screen"
    screen_cache.mkdir(parents=True)
    cache_root.chmod(0o755)
    screen_cache.chmod(0o700)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 0
    assert '"action":"upgrade"' in capsys.readouterr().out
    assert cache_root.stat().st_mode & 0o777 == 0o700
    assert screen_cache.stat().st_mode & 0o777 == 0o700


def test_upgrade_cli_refuses_unsafe_legacy_cache_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    cache_parent = tmp_path / "Library" / "Caches"
    cache_parent.mkdir(parents=True)
    unsafe_target = tmp_path / "unsafe-cache"
    unsafe_target.mkdir()
    (cache_parent / "galaxy-control").symlink_to(unsafe_target)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 1
    output = capsys.readouterr().out
    assert '"code":"cache_migration_unsafe"' in output
    assert (destination / "SKILL.md").read_text() == "old"


def test_upgrade_cli_refuses_cache_path_swapped_during_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    cache_root = tmp_path / "Library" / "Caches" / "galaxy-control"
    cache_root.mkdir(parents=True)
    cache_root.chmod(0o755)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    unrelated.chmod(0o755)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    original_fchmod = os.fchmod

    def swap_path_before_fchmod(descriptor: int, mode: int) -> None:
        cache_root.rmdir()
        cache_root.symlink_to(unrelated, target_is_directory=True)
        original_fchmod(descriptor, mode)

    monkeypatch.setattr(os, "fchmod", swap_path_before_fchmod)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 1
    assert '"code":"cache_migration_unsafe"' in capsys.readouterr().out
    assert unrelated.stat().st_mode & 0o777 == 0o755
    assert (destination / "SKILL.md").read_text() == "old"


def test_upgrade_cli_refuses_cache_path_swapped_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    cache_root = tmp_path / "Library" / "Caches" / "galaxy-control"
    cache_root.mkdir(parents=True)
    cache_root.chmod(0o755)
    detached = tmp_path / "detached-cache"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    original_open = os.open

    def swap_path_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
    ) -> int:
        if Path(path) == cache_root:
            cache_root.rename(detached)
            cache_root.mkdir()
            cache_root.chmod(0o755)
        return original_open(path, flags)

    monkeypatch.setattr(os, "open", swap_path_before_open)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 1
    assert '"code":"cache_migration_unsafe"' in capsys.readouterr().out
    assert cache_root.stat().st_mode & 0o777 == 0o755
    assert (destination / "SKILL.md").read_text() == "old"


def test_upgrade_cli_reports_cache_open_failure_as_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    destination = tmp_path / ".codex" / "skills" / "galaxy-control"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("old")
    cache_root = tmp_path / "Library" / "Caches" / "galaxy-control"
    cache_root.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    original_open = os.open

    def denied_open(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int) -> int:
        if Path(path) == cache_root:
            raise PermissionError("simulated cache denial")
        return original_open(path, flags)

    monkeypatch.setattr(os, "open", denied_open)

    # When
    exit_code = main(("--upgrade", "--approved"))

    # Then
    assert exit_code == 1
    output = capsys.readouterr().out
    assert '"code":"cache_migration_failed"' in output
    assert (destination / "SKILL.md").read_text() == "old"
