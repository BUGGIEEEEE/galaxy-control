"""Strict request-to-argv reduction for reviewed OpenMinis device controls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeVar

from .protocol import Action, BridgeError, JsonObject, JsonValue, parse_object

MAX_COORDINATE: Final = 10_000
MAX_TEXT_LENGTH: Final = 2_048
PACKAGE_PATTERN: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")
EnumValue = TypeVar("EnumValue", bound=StrEnum)


class Executable(StrEnum):
    """One reviewed OpenMinis executable, or no executable for health."""

    NONE = "none"
    SHIZUKU = "shizuku"
    A11Y = "a11y"


class InputKey(StrEnum):
    """Global keys deliberately allowed through Accessibility."""

    BACK = "BACK"
    HOME = "HOME"
    RECENTS = "RECENTS"
    NOTIFICATIONS = "NOTIFICATIONS"


class ScrollDirection(StrEnum):
    """Directions supported by the reviewed Accessibility scroll wrapper."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """A fully validated action reduced to one literal executable argv."""

    action: Action
    executable: Executable
    argv: tuple[str, ...]


NO_ARGUMENT_COMMANDS: Final = {
    Action.HEALTH: (Executable.NONE, ()),
    Action.SHIZUKU_STATUS: (Executable.SHIZUKU, ("service", "status", "--compact")),
    Action.DEVICE_INFO: (Executable.SHIZUKU, ("device", "info", "--compact")),
    Action.BATTERY: (Executable.SHIZUKU, ("device", "battery", "--compact")),
    Action.A11Y_STATUS: (Executable.A11Y, ("service", "status", "--compact")),
    Action.UI_DUMP: (Executable.A11Y, ("ui", "dump", "--compact")),
    Action.UI_INFO: (Executable.A11Y, ("ui", "info", "--compact")),
    Action.TOP_ACTIVITY: (Executable.SHIZUKU, ("activity", "top", "--compact")),
}


def _invalid(message: str = "action arguments are invalid") -> BridgeError:
    return BridgeError(400, "invalid_request", message)


def _exact_args(payload: JsonObject, expected: frozenset[str]) -> JsonObject:
    if not payload.has_exact_keys(frozenset(("action", "args"))):
        raise _invalid()
    arguments = payload.value("args")
    if not isinstance(arguments, JsonObject) or not arguments.has_exact_keys(expected):
        raise _invalid()
    return arguments


def _integer(arguments: JsonObject, key: str, *, minimum: int = 0) -> int:
    value = arguments.value(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid()
    if not minimum <= value <= MAX_COORDINATE:
        raise _invalid()
    return value


def _text(arguments: JsonObject, key: str, *, package: bool = False) -> str:
    value = arguments.value(key)
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_TEXT_LENGTH:
        raise _invalid()
    if package and PACKAGE_PATTERN.fullmatch(value) is None:
        raise _invalid()
    return value


def _enum_value(arguments: JsonObject, key: str, enum_type: type[EnumValue]) -> EnumValue:
    value = arguments.value(key)
    if not isinstance(value, str):
        raise _invalid()
    try:
        return enum_type(value)
    except ValueError as error:
        raise _invalid() from error


def fixed_request(action: Action) -> CommandRequest:
    """Build one no-argument request already fixed by the bridge source."""
    try:
        executable, argv = NO_ARGUMENT_COMMANDS[action]
    except KeyError as error:
        raise _invalid() from error
    return CommandRequest(action, executable, argv)


def _argument_request(action: Action, payload: JsonObject) -> CommandRequest:
    match action:
        case Action.TAP_XY:
            args = _exact_args(payload, frozenset(("x", "y")))
            argv = ("tap", "xy", str(_integer(args, "x")), str(_integer(args, "y")), "--compact")
            return CommandRequest(action, Executable.A11Y, argv)
        case Action.TAP_TEXT | Action.INPUT_TEXT:
            args = _exact_args(payload, frozenset(("text",)))
            prefix = ("tap", "text") if action is Action.TAP_TEXT else ("input", "text")
            return CommandRequest(
                action, Executable.A11Y, (*prefix, _text(args, "text"), "--compact")
            )
        case Action.INPUT_KEY:
            args = _exact_args(payload, frozenset(("key",)))
            key = _enum_value(args, "key", InputKey)
            return CommandRequest(action, Executable.A11Y, ("input", "key", key.value, "--compact"))
        case Action.SCROLL_XY:
            args = _exact_args(payload, frozenset(("x", "y", "direction", "distance")))
            direction = _enum_value(args, "direction", ScrollDirection)
            argv = (
                "scroll",
                "xy",
                str(_integer(args, "x")),
                str(_integer(args, "y")),
                "--direction",
                direction.value,
                "--distance",
                str(_integer(args, "distance", minimum=1)),
                "--compact",
            )
            return CommandRequest(action, Executable.A11Y, argv)
        case Action.OPEN_APP:
            args = _exact_args(payload, frozenset(("package",)))
            package = _text(args, "package", package=True)
            return CommandRequest(
                action, Executable.SHIZUKU, ("activity", "start", "-p", package, "--compact")
            )
        case Action.HEALTH | Action.SHIZUKU_STATUS | Action.DEVICE_INFO | Action.BATTERY:
            raise _invalid()
        case Action.A11Y_STATUS | Action.UI_DUMP | Action.UI_INFO | Action.TOP_ACTIVITY:
            raise _invalid()


def parse_request(raw: bytes) -> CommandRequest:
    """Parse one exact request and reduce all values to fixed, non-shell argv."""
    payload = parse_object(raw)
    try:
        action_value: JsonValue = payload.value("action")
    except KeyError as error:
        raise _invalid() from error
    if not isinstance(action_value, str):
        raise _invalid()
    try:
        action = Action(action_value)
    except ValueError as error:
        raise BridgeError(400, "invalid_action", "action is not supported") from error
    if action in NO_ARGUMENT_COMMANDS:
        if not payload.has_exact_keys(frozenset(("action",))):
            raise _invalid()
        return fixed_request(action)
    return _argument_request(action, payload)
