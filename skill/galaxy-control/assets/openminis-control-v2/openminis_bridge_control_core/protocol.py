"""Typed request and fixed-command response protocol boundaries."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NoReturn, TypeAlias, cast

MAX_JSON_DEPTH: Final = 64


class Action(StrEnum):
    """Remote actions exposed through reviewed OpenMinis device CLIs."""

    HEALTH = "health"
    SHIZUKU_STATUS = "shizuku_status"
    DEVICE_INFO = "device_info"
    BATTERY = "battery"
    A11Y_STATUS = "a11y_status"
    UI_DUMP = "ui_dump"
    UI_INFO = "ui_info"
    TOP_ACTIVITY = "top_activity"
    TAP_XY = "tap_xy"
    TAP_TEXT = "tap_text"
    INPUT_TEXT = "input_text"
    INPUT_KEY = "input_key"
    SCROLL_XY = "scroll_xy"
    OPEN_APP = "open_app"


@dataclass(frozen=True, slots=True)
class BridgeError(Exception):
    """Stable HTTP or lifecycle error safe to return to an owner."""

    status: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class JsonObject:
    """A JSON object that preserves exact keys after one decoder pass."""

    pairs: tuple[tuple[str, JsonValue], ...]

    def value(self, key: str) -> JsonValue:
        """Return the already decoded value for a declared object key."""
        for candidate, value in self.pairs:
            if candidate == key:
                return value
        raise KeyError(key)

    def has_exact_keys(self, expected: frozenset[str]) -> bool:
        """Check the object contains every and only the declared protocol keys."""
        keys = frozenset(key for key, _ in self.pairs)
        return len(self.pairs) == len(expected) and keys == expected


JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | JsonObject | None


class _DuplicateJsonKeyError(ValueError):
    """Raised when one JSON object repeats a key."""


class _InvalidJsonNumberError(ValueError):
    """Raised when input uses a non-standard or non-finite JSON number."""


class _JsonDepthError(ValueError):
    """Raised before decoding an excessively nested JSON document."""


def _reject_json_constant(_value: str) -> NoReturn:
    raise _InvalidJsonNumberError


def _parse_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _InvalidJsonNumberError
    return parsed


def _json_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    keys = {key for key, _ in pairs}
    if len(keys) != len(pairs):
        raise _DuplicateJsonKeyError
    return JsonObject(tuple(pairs))


def _decode_text(raw: str | bytes) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def _check_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise _JsonDepthError
        elif character in "]}":
            depth -= 1


def _decode_object(raw: str | bytes) -> JsonObject:
    text = _decode_text(raw)
    _check_json_depth(text)
    if not text.lstrip().startswith("{"):
        raise TypeError
    root: dict[str, JsonObject] = {}

    def collect(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
        decoded = _json_object(pairs)
        root["value"] = decoded
        return decoded

    decoded = cast(
        "object",
        json.loads(
            text,
            object_pairs_hook=collect,
            parse_constant=_reject_json_constant,
            parse_float=_parse_json_float,
        ),
    )
    if not isinstance(decoded, JsonObject):
        raise TypeError
    return root["value"]


def parse_object(raw: bytes) -> JsonObject:
    """Decode one duplicate-free JSON object from an untrusted request body."""
    try:
        return _decode_object(raw)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _InvalidJsonNumberError,
        _JsonDepthError,
        RecursionError,
    ) as error:
        raise BridgeError(400, "invalid_json", "request body must be valid JSON") from error
    except (_DuplicateJsonKeyError, TypeError) as error:
        raise BridgeError(400, "invalid_request", "request body is invalid") from error


def validate_cli_output(raw: str | bytes) -> str:
    """Accept only the fixed command's complete success envelope."""
    try:
        text = _decode_text(raw)
        envelope = _decode_object(text)
    except (
        _DuplicateJsonKeyError,
        _InvalidJsonNumberError,
        _JsonDepthError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise BridgeError(
            502, "invalid_cli_output", "device command returned invalid JSON"
        ) from error
    if not envelope.has_exact_keys(frozenset(("ok", "data"))):
        raise BridgeError(502, "invalid_cli_output", "device command returned invalid JSON")
    if envelope.value("ok") is not True or not isinstance(envelope.value("data"), JsonObject):
        raise BridgeError(502, "invalid_cli_output", "device command returned invalid JSON")
    return text
