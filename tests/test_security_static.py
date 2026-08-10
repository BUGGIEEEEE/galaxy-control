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
