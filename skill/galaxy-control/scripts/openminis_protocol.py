"""Typed fixed command surface for OpenMinis Control v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, assert_never

from galaxy_process import JsonObject

MAX_COORDINATE: Final = 10_000
MAX_TEXT_LENGTH: Final = 2_048


@unique
class Action(StrEnum):
    HEALTH = "health"
    SHIZUKU_STATUS = "shizuku_status"
    DEVICE_INFO = "device_info"
    BATTERY = "battery"
    A11Y_STATUS = "a11y_status"
    UI_INFO = "ui_info"
    UI_DUMP = "ui_dump"
    INPUT_KEY = "input_key"
    TAP_TEXT = "tap_text"
    TAP_XY = "tap_xy"
    INPUT_TEXT = "input_text"
    SCROLL_XY = "scroll_xy"


@unique
class InputKey(StrEnum):
    BACK = "BACK"
    HOME = "HOME"
    RECENTS = "RECENTS"
    NOTIFICATIONS = "NOTIFICATIONS"


@unique
class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class ProtocolError(Exception):
    """Invalid local command before any bridge request."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class Coordinates:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class Text:
    value: str


@dataclass(frozen=True, slots=True)
class Key:
    value: InputKey


@dataclass(frozen=True, slots=True)
class Scroll:
    x: int
    y: int
    direction: Direction
    distance: int


Arguments = Coordinates | Text | Key | Scroll


@dataclass(frozen=True, slots=True)
class BridgeRequest:
    action: Action
    arguments: Arguments | None = None

    def body(self) -> JsonObject:
        """Serialize only the fixed wire keys for this request."""
        body: JsonObject = {"action": self.action.value}
        match self.arguments:
            case None:
                return body
            case Coordinates(x=x, y=y):
                args: JsonObject = {"x": x, "y": y}
            case Text(value=value):
                args = {"text": value}
            case Key(value=value):
                args = {"key": value.value}
            case Scroll(x=x, y=y, direction=direction, distance=distance):
                args = {"x": x, "y": y, "direction": direction.value, "distance": distance}
            case unreachable:
                assert_never(unreachable)
        body["args"] = args
        return body


def _coordinate(raw: str) -> int:
    if not raw.isdecimal():
        raise ProtocolError("coordinate_invalid", "coordinates must be decimal integers")
    value = int(raw)
    if value > MAX_COORDINATE:
        raise ProtocolError("coordinate_invalid", "coordinates must be between 0 and 10000")
    return value


def _text(raw: str) -> str:
    if not 1 <= len(raw) <= MAX_TEXT_LENGTH:
        raise ProtocolError("text_invalid", "text must contain 1 to 2048 characters")
    return raw


def parse_command(argv: tuple[str, ...]) -> BridgeRequest:
    """Parse one exact OpenMinis CLI command."""
    match argv:  # noqa: V001  # noqa: MATCH_OK -- reject unknown forms.
        case ("health",):
            return BridgeRequest(Action.HEALTH)
        case ("shizuku-status",):
            return BridgeRequest(Action.SHIZUKU_STATUS)
        case ("device-info",):
            return BridgeRequest(Action.DEVICE_INFO)
        case ("battery",):
            return BridgeRequest(Action.BATTERY)
        case ("a11y-status",):
            return BridgeRequest(Action.A11Y_STATUS)
        case ("ui-info",):
            return BridgeRequest(Action.UI_INFO)
        case ("ui-dump",):
            return BridgeRequest(Action.UI_DUMP)
        case ("input-key", raw_key):
            try:
                key = InputKey(raw_key)
            except ValueError as error:
                raise ProtocolError("key_invalid", "input key is not allowed") from error
            return BridgeRequest(Action.INPUT_KEY, Key(key))
        case ("tap-text", raw_text):
            return BridgeRequest(Action.TAP_TEXT, Text(_text(raw_text)))
        case ("input-text", raw_text):
            return BridgeRequest(Action.INPUT_TEXT, Text(_text(raw_text)))
        case ("tap-xy", raw_x, raw_y):
            return BridgeRequest(Action.TAP_XY, Coordinates(_coordinate(raw_x), _coordinate(raw_y)))
        case ("scroll-xy", raw_x, raw_y, raw_direction, raw_distance):
            try:
                direction = Direction(raw_direction)
            except ValueError as error:
                raise ProtocolError(
                    "direction_invalid", "scroll direction is not allowed"
                ) from error
            distance = _coordinate(raw_distance)
            if distance == 0:
                raise ProtocolError(
                    "distance_invalid", "scroll distance must be between 1 and 10000"
                )
            return BridgeRequest(
                Action.SCROLL_XY,
                Scroll(_coordinate(raw_x), _coordinate(raw_y), direction, distance),
            )
        case _:
            raise ProtocolError("invalid_request", "unsupported OpenMinis command or arguments")
