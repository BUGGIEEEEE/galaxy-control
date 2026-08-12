from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON_ROOTS = (ROOT / "skill" / "galaxy-control" / "scripts", ROOT / "scripts")


def python_sources() -> tuple[Path, ...]:
    return tuple(path for root in PYTHON_ROOTS for path in root.glob("*.py"))


def test_every_subprocess_call_sets_literal_shell_false() -> None:
    # Given
    calls: list[tuple[Path, ast.Call]] = []
    for path in python_sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr in {"run", "Popen"}
            ):
                calls.append((path, node))

    # When / Then
    assert calls
    for path, call in calls:
        shell = next((keyword.value for keyword in call.keywords if keyword.arg == "shell"), None)
        assert isinstance(shell, ast.Constant), path
        assert shell.value is False, path


def test_executable_python_exposes_no_broad_process_or_shell_command() -> None:
    # Given
    source = "\n".join(path.read_text() for path in python_sources())

    # When / Then
    assert "killall" not in source
    assert "pkill" not in source
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "ctl.restart" not in source
    assert "setprop" not in source


def test_oneui_artifact_checkers_cannot_issue_phone_or_shell_commands() -> None:
    # Given
    names = ("oneui_inventory.py", "oneui_inventory_core.py", "oneui_ledger.py")
    source = "\n".join(
        (ROOT / "skill" / "galaxy-control" / "scripts" / name).read_text() for name in names
    )

    # When / Then
    assert "import subprocess" not in source
    assert "galaxy_control.sh" not in source
    assert "adb " not in source
    assert "scrcpy" not in source
    assert "shell=" not in source


def test_openminis_wrapper_does_not_scan_or_repair_quarantine_per_call() -> None:
    # Given
    source = (ROOT / "skill" / "galaxy-control" / "scripts" / "galaxy_control.sh").read_text()

    # When / Then
    assert "runtime-quarantine-guard" not in source
    assert "xattr" not in source
    assert " repair " not in source
