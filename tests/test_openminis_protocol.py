from __future__ import annotations

import pytest

from openminis_protocol import ProtocolError, parse_command


@pytest.mark.parametrize(
    ("argv", "action"),
    [
        (("health",), "health"),
        (("a11y-status",), "a11y_status"),
        (("ui-info",), "ui_info"),
        (("ui-dump",), "ui_dump"),
        (("input-key", "BACK"), "input_key"),
        (("tap-text", "Settings"), "tap_text"),
        (("tap-xy", "500", "900"), "tap_xy"),
        (("scroll-xy", "500", "900", "down", "1200"), "scroll_xy"),
    ],
)
def test_fixed_command_builds_expected_action(argv: tuple[str, ...], action: str) -> None:
    # Given / When
    request = parse_command(argv)

    # Then
    assert request.body()["action"] == action


def test_input_text_does_not_add_send_action() -> None:
    # Given / When
    request = parse_command(("input-text", "draft only"))

    # Then
    assert request.body() == {"action": "input_text", "args": {"text": "draft only"}}


@pytest.mark.parametrize(
    "argv",
    [
        ("open-app", "com.example.app"),
        ("input-key", "ENTER"),
        ("tap-xy", "-1", "5"),
        ("tap-xy", "5;touch", "5"),
        ("scroll-xy", "1", "2", "diagonal", "3"),
        ("health", "--url", "http://example.invalid"),
    ],
)
def test_arbitrary_or_unsafe_command_is_rejected(argv: tuple[str, ...]) -> None:
    # Given / When / Then
    with pytest.raises(ProtocolError):
        parse_command(argv)


def test_oversized_text_is_rejected() -> None:
    # Given / When / Then
    with pytest.raises(ProtocolError, match="2048"):
        parse_command(("input-text", "x" * 2049))
