#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx2[http2,brotli,zstd]",
#     "pydantic>=2,<3",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed): brew install uv
# 2. Run: uv run openminis_client.py health
# 3. Or make executable and run: chmod +x openminis_client.py && ./openminis_client.py health
# ──────────────────

"""Authenticated fixed-action OpenMinis client for one enrolled Galaxy."""

from __future__ import annotations

import json
import math
import os
import re
import socket
import sys
from dataclasses import dataclass
from typing import Annotated, ClassVar, Final, Literal, NoReturn, assert_never, cast

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, ValidationError
from pydantic import JsonValue as PydanticJsonValue

from galaxy_process import JsonObject, JsonValue, RouteMetadata, with_route
from galaxy_profile import ProfileError, load_profile
from openminis_protocol import Action, BridgeRequest, ProtocolError, parse_command

AUTH_ENV: Final = "OPENMINIS_BRIDGE_TOKEN"
TOKEN_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_RESPONSE_BYTES: Final = 1_048_576
LIMITS: Final = httpx2.Limits(
    max_connections=200,
    max_keepalive_connections=40,
    keepalive_expiry=30.0,
)
TIMEOUT: Final = httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
SOCKET_OPTIONS: Final = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]


@dataclass(frozen=True, slots=True)
class ClientError(Exception):
    """Stable OpenMinis client boundary failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ErrorDetail(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=512)


class SuccessResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    ok: Literal[True]
    action: Action
    result: PydanticJsonValue


class ErrorResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    ok: Literal[False]
    error: ErrorDetail


ResponseEnvelope = Annotated[SuccessResponse | ErrorResponse, Field(discriminator="ok")]
RESPONSE_ADAPTER: Final[TypeAdapter[ResponseEnvelope]] = TypeAdapter(ResponseEnvelope)


class DuplicateJsonKeyError(ValueError):
    """Bridge response repeated an object key."""


class InvalidJsonNumberError(ValueError):
    """Bridge response contained a non-finite JSON number."""


def _reject_constant(_value: str) -> NoReturn:
    raise InvalidJsonNumberError


def _parse_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise InvalidJsonNumberError
    return value


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise DuplicateJsonKeyError
    return dict(pairs)


def parse_response(content: bytes, expected_action: Action) -> SuccessResponse:
    """Parse a strict response envelope and require the requested action."""
    try:
        decoded = cast(
            "object",
            json.loads(
                content,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
                parse_float=_parse_float,
            ),
        )
        envelope = RESPONSE_ADAPTER.validate_python(decoded)
    except (UnicodeDecodeError, ValueError, ValidationError, RecursionError) as error:
        raise ClientError("invalid_response", "bridge returned invalid JSON envelope") from error
    match envelope:
        case ErrorResponse(error=detail):
            raise ClientError(detail.code, detail.message)
        case SuccessResponse(action=returned):
            if returned is not expected_action:
                raise ClientError(
                    "action_mismatch", "bridge response action does not match request"
                )
            if not isinstance(envelope.result, dict) or "route" in envelope.result:
                raise ClientError(
                    "invalid_response",
                    "bridge success result must be an object without reserved route metadata",
                )
            result = cast("JsonObject", envelope.result)
            is_action = expected_action in {
                Action.INPUT_KEY,
                Action.TAP_TEXT,
                Action.TAP_XY,
                Action.INPUT_TEXT,
                Action.SCROLL_XY,
            }
            routed = with_route(
                result,
                RouteMetadata(
                    controller="openminis",
                    transport="tailscale_http",
                    role="act" if is_action else "observe",
                    verification_required=is_action,
                    verify_with=("openminis", "adb") if is_action else (),
                ),
            )
            return SuccessResponse(ok=True, action=envelope.action, result=routed)
        case unreachable:
            assert_never(unreachable)


def read_token() -> SecretStr | None:
    """Read an optional compatibility token only from the process environment."""
    token = os.environ.get(AUTH_ENV)
    if token is None:
        return None
    if TOKEN_PATTERN.fullmatch(token) is None:
        raise ClientError("token_invalid", "bridge token must be 64 lowercase hex characters")
    return SecretStr(token)


def create_client(base_url: str, token: SecretStr | None) -> httpx2.Client:
    """Create a bounded client that refuses proxies and redirects."""
    headers = {"Authorization": f"Bearer {token.get_secret_value()}"} if token is not None else {}
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=LIMITS,
        socket_options=SOCKET_OPTIONS,
    )
    return httpx2.Client(
        transport=transport,
        timeout=TIMEOUT,
        base_url=base_url,
        headers=headers,
        follow_redirects=False,
        trust_env=False,
    )


def call_bridge(request: BridgeRequest) -> SuccessResponse:
    """Call one fixed bridge action against the enrolled literal origin."""
    profile = load_profile()
    try:
        with (
            create_client(profile.openminis_origin, read_token()) as client,
            client.stream("POST", "/v1/call", json=request.body()) as response,
        ):
            if response.is_redirect:
                raise ClientError("redirect_refused", "bridge redirect was refused")
            content = bytearray()
            for chunk in response.iter_bytes():
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ClientError("response_too_large", "bridge response exceeds size limit")
                content.extend(chunk)
    except httpx2.RequestError as error:
        raise ClientError("network_error", type(error).__name__) from None
    if response.status_code != 200:
        raise ClientError("http_error", f"bridge returned HTTP {response.status_code}")
    return parse_response(bytes(content), request.action)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Run one fixed OpenMinis command."""
    try:
        request = parse_command(tuple(sys.argv[1:] if argv is None else argv))
        response = call_bridge(request)
    except (ProtocolError, ProfileError, ClientError) as error:
        _ = sys.stderr.write(f"error:{error.code}:{error.message}\n")
        return 1
    encoded = response.model_dump_json(exclude_none=True)
    _ = sys.stdout.write(encoded + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
