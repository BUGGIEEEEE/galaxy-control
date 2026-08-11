"""Authenticated HTTP serving for OpenMinis Control v2."""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import shutil
import signal
import socket
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, ClassVar, Final, NoReturn, final

from .actions import CommandRunner
from .network import BridgeNetwork
from .protocol import BridgeError
from .requests import parse_request

if TYPE_CHECKING:
    from types import FrameType

MAX_BODY_BYTES: Final = 4_096
REQUEST_DEADLINE_SECONDS: Final = 2.0


@dataclass(frozen=True, slots=True)
class Runtime:
    """Immutable server authentication and command-execution state."""

    token: str
    network: BridgeNetwork
    runner: CommandRunner


def client_allowed(address: str, network: BridgeNetwork) -> bool:
    """Allow loopback, the phone itself, or the enrolled Mac tailnet peer."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return isinstance(parsed, ipaddress.IPv4Address) and (
        parsed.is_loopback or address in {network.phone_ipv4, network.trusted_mac_ipv4}
    )


def bind_allowed(host: str, network: BridgeNetwork) -> bool:
    """Allow a listener only on loopback or the enrolled phone tailnet address."""
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    return isinstance(parsed, ipaddress.IPv4Address) and (
        parsed.is_loopback or address_equal(host, network.phone_ipv4)
    )


def address_equal(first: str, second: str) -> bool:
    """Compare two already parsed IPv4 spellings."""
    return ipaddress.IPv4Address(first) == ipaddress.IPv4Address(second)


def authorize_client(address: str, authorization: str, runtime: Runtime) -> None:
    """Authorize one request using its enrolled source and optional bearer token."""
    if not client_allowed(address, runtime.network):
        raise BridgeError(403, "source_forbidden", "client address is not allowed")
    if address_equal(address, runtime.network.trusted_mac_ipv4):
        return
    candidate = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(candidate, runtime.token):
        raise BridgeError(401, "unauthorized", "valid bearer token required")


@final
class BridgeHandler(BaseHTTPRequestHandler):
    """Authenticated POST-only handler with an absolute connection deadline."""

    runtime: ClassVar[Runtime]
    connection: socket.socket
    _deadline: threading.Timer | None = None

    def setup(self) -> None:
        super().setup()
        self._deadline = threading.Timer(REQUEST_DEADLINE_SECONDS, self._expire_connection)
        self._deadline.daemon = True
        self._deadline.start()

    def finish(self) -> None:
        self._cancel_deadline()
        super().finish()

    def _cancel_deadline(self) -> None:
        if self._deadline is not None:
            self._deadline.cancel()
            self._deadline = None

    def _expire_connection(self) -> None:
        with suppress(OSError):
            self.connection.shutdown(socket.SHUT_RDWR)

    def _guard(self) -> None:
        authorize_client(
            self.client_address[0],
            self.headers.get("Authorization", ""),
            self.runtime,
        )

    def _write(self, status: int, encoded: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "POST")
        self.end_headers()
        _ = self.wfile.write(encoded)

    def _send_error(self, error: BridgeError) -> None:
        payload = {"ok": False, "error": {"code": error.code, "message": error.message}}
        self._write(error.status, json.dumps(payload, separators=(",", ":")).encode())

    def log_message(self, format: str, *args: str | int) -> None:  # noqa: A002
        """Keep all request metadata out of the persistent owner log."""
        _ = format, args

    def _handle_call(self) -> None:
        self._guard()
        if self.command != "POST":
            raise BridgeError(405, "method_not_allowed", "only POST is supported")
        if self.path != "/v1/call":
            raise BridgeError(404, "not_found", "endpoint not found")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise BridgeError(411, "length_required", "Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise BridgeError(400, "invalid_length", "Content-Length must be an integer") from error
        if length < 0 or length > MAX_BODY_BYTES:
            raise BridgeError(413, "request_too_large", "request body exceeds the limit")
        request = parse_request(self.rfile.read(length))
        self._cancel_deadline()
        result = self.runtime.runner.run(request)
        action_json = json.dumps(request.action.value)
        self._write(200, f'{{"ok":true,"action":{action_json},"result":{result}}}'.encode())

    def do_POST(self) -> None:
        """Handle the only supported HTTP operation."""
        try:
            try:
                self._handle_call()
            except BridgeError as error:
                self._send_error(error)
        except (BrokenPipeError, ConnectionError, TimeoutError):
            return

    do_GET = do_HEAD = do_OPTIONS = do_PUT = do_DELETE = do_PATCH = do_TRACE = do_CONNECT = (  # noqa: N815
        do_POST
    )


def _shutdown(_signum: int, _frame: FrameType | None) -> NoReturn:
    BridgeHandler.runtime.runner.terminate()
    raise SystemExit(0)


def serve(network: BridgeNetwork, token: str, ready_fd: int | None) -> None:
    """Bind the enrolled phone address and serve requests sequentially."""
    if not bind_allowed(network.phone_ipv4, network):
        raise BridgeError(1, "invalid_bind", "phone bind address is invalid")
    shizuku_cli = os.environ.get("OPENMINIS_SHIZUKU_CLI", "android-shizuku-cli")
    a11y_cli = os.environ.get("OPENMINIS_A11Y_CLI", "android-a11y-cli")
    BridgeHandler.runtime = Runtime(
        token,
        network,
        CommandRunner(shutil.which(shizuku_cli), shutil.which(a11y_cli)),
    )
    _ = signal.signal(signal.SIGTERM, _shutdown)
    try:
        server = HTTPServer((network.phone_ipv4, network.port), BridgeHandler)
    except OSError as error:
        raise BridgeError(1, "bind_failed", "bridge listener could not start") from error
    with server:
        if ready_fd is not None:
            _ = os.write(ready_fd, b"R")
            os.close(ready_fd)
        _ = sys.stderr.write("bridge listening on enrolled tailnet address\n")
        _ = sys.stderr.flush()
        _ = server.serve_forever()
