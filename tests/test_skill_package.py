from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

SKILL_ROOT = Path(__file__).parent.parent / "skill" / "galaxy-control"
REPOSITORY_ROOT = SKILL_ROOT.parent.parent


def test_skill_manifest_is_bounded_and_names_the_skill() -> None:
    # Given
    content = (SKILL_ROOT / "SKILL.md").read_text()

    # When
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", content, re.DOTALL)

    # Then
    assert frontmatter is not None
    assert 'name: "galaxy-control"' in frontmatter.group(1)
    assert "description:" in frontmatter.group(1)
    assert len(content.splitlines()) < 500


def test_skill_version_matches_distribution_version() -> None:
    # Given
    metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())

    # When / Then
    assert (SKILL_ROOT / "VERSION").read_text().strip() == metadata["project"]["version"]


def test_every_reference_linked_from_skill_exists() -> None:
    # Given
    content = (SKILL_ROOT / "SKILL.md").read_text()

    # When
    linked = set(re.findall(r"\(references/([a-z0-9-]+\.md)\)", content))
    actual = {path.name for path in (SKILL_ROOT / "references").glob("*.md")}

    # Then
    assert linked == actual


def test_agent_metadata_mentions_explicit_skill_prompt() -> None:
    # Given / When
    content = (SKILL_ROOT / "agents" / "openai.yaml").read_text()

    # Then
    assert 'display_name: "Galaxy Control"' in content
    assert "$galaxy-control" in content
    assert "allow_implicit_invocation: true" in content
    assert 'session: ["scripts/galaxy_doctor.py", "all"]' in content
    assert 'openminis: ["scripts/galaxy_doctor.py", "openminis"]' in content
    assert 'adb: ["scripts/galaxy_doctor.py", "adb"]' in content
    assert 'scrcpy: ["scripts/galaxy_doctor.py", "scrcpy"]' in content
    assert (
        'paired_adb_prepare: ["scripts/galaxy_remote_adb.py", "wireless-prepare", "--approved"]'
    ) in content
    assert (
        'paired_adb_opt_in: ["scripts/galaxy_setup.py", "enable-auto-reconnect", "--approved"]'
    ) in content
    assert (
        'connection_port_sources: ["current_shizuku_launcher_output", '
        '"openminis_wireless_debugging_read_only"]'
    ) in content
    assert 'steady_adb_probe: ["scripts/galaxy_remote_adb.py", "connect"]' in content
    assert (
        'steady_adb_promote: ["scripts/galaxy_remote_adb.py", '
        '"legacy-enable-from-wireless", "--port", "CURRENT_CONNECTION_PORT", "--approved"]'
    ) in content
    assert 'steady_adb_final_endpoint: "profile.steady_endpoint"' in content
    assert 'scrcpy_launch_check: ["scripts/galaxy_screen.py", "doctor"]' in content
    assert 'session_reuse: "memory_only"' in content
    assert 'result_route_field: "result.route"' in content


def test_entry_scripts_are_executable_and_have_pep723_metadata() -> None:
    # Given
    entries = (
        "galaxy_doctor.py",
        "galaxy_bridge_package.py",
        "galaxy_remote_adb.py",
        "galaxy_screen.py",
        "galaxy_setup.py",
        "oneui_inventory.py",
        "oneui_ledger.py",
        "openminis_client.py",
    )

    # When / Then
    for name in entries:
        path = SKILL_ROOT / "scripts" / name
        content = path.read_text()
        assert os.access(path, os.X_OK)
        assert content.startswith("#!/usr/bin/env -S uv run --script\n# /// script\n")


def test_readme_embeds_all_privacy_clean_flow_diagrams() -> None:
    # Given
    content = (REPOSITORY_ROOT / "README.md").read_text()
    expected = {
        "docs/images/galaxy-flow-1-v040.svg",
        "docs/images/galaxy-flow-2-v040.svg",
        "docs/images/galaxy-flow-3-v040.svg",
    }

    # When
    linked = set(re.findall(r"!\[[^]]+\]\((docs/images/galaxy-flow-[123]-v040\.svg)\)", content))

    # Then
    assert linked == expected
    for relative in linked:
        diagram = (REPOSITORY_ROOT / relative).read_text()
        assert diagram.startswith("<svg ")
        assert "<title " in diagram
        assert "<desc " in diagram
