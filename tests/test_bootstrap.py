from __future__ import annotations

from collections.abc import Callable

from bootstrap import BootstrapRuntime, CommandResult, execute


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...]) -> CommandResult:
        self.calls.append(argv)
        return self.responses.pop(0)


def runtime(runner: FakeRunner, which: Callable[[str], str | None]) -> BootstrapRuntime:
    return BootstrapRuntime(runner, which)


def test_bootstrap_doctor_plans_uv_without_mutating() -> None:
    # Given
    runner = FakeRunner([])
    available = {"brew": "/opt/homebrew/bin/brew"}

    # When
    envelope, exit_code = execute(("doctor",), runtime(runner, available.get))

    # Then
    assert exit_code == 0
    assert envelope["result"]["status"] == "NEEDS_APPROVAL"
    assert envelope["result"]["install_command"] == [
        "/opt/homebrew/bin/brew",
        "install",
        "uv",
    ]
    assert runner.calls == []


def test_bootstrap_apply_installs_only_missing_uv_after_approval() -> None:
    # Given
    runner = FakeRunner([CommandResult(0, "installed", "")])
    available = {"brew": "/opt/homebrew/bin/brew"}

    # When
    envelope, exit_code = execute(("apply", "--approved"), runtime(runner, available.get))

    # Then
    assert exit_code == 0
    assert envelope["result"]["installed"] is True
    assert runner.calls == [("/opt/homebrew/bin/brew", "install", "uv")]


def test_bootstrap_never_updates_existing_uv() -> None:
    # Given
    runner = FakeRunner([])
    available = {"brew": "/opt/homebrew/bin/brew", "uv": "/opt/homebrew/bin/uv"}

    # When
    envelope, exit_code = execute(("apply", "--approved"), runtime(runner, available.get))

    # Then
    assert exit_code == 0
    assert envelope["result"]["installed"] is False
    assert envelope["result"]["status"] == "READY"
    assert runner.calls == []


def test_bootstrap_requires_approval_and_homebrew() -> None:
    # Given
    runner = FakeRunner([])

    # When
    denied, denied_code = execute(("apply",), runtime(runner, lambda _name: None))
    blocked, blocked_code = execute(("doctor",), runtime(runner, lambda _name: None))

    # Then
    assert denied_code == 1
    assert denied["error"]["code"] == "approval_required"
    assert blocked_code == 0
    assert blocked["result"]["status"] == "NEEDS_USER_ACTION"
    assert blocked["result"]["user_actions"] == ["install_homebrew_or_uv_manually"]
    assert runner.calls == []
