from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from galaxy_bridge_builder import BridgeIdentity, build_bridge_package

ROOT = Path(__file__).parent.parent
ASSET_ROOT = ROOT / "skill" / "galaxy-control" / "assets" / "openminis-control-v2"
RUNTIME_SOURCES = tuple(
    path for path in ASSET_ROOT.rglob("*.py") if path.name != "installer_template.py"
)


def _fresh_core(monkeypatch: pytest.MonkeyPatch, state_home: Path) -> ModuleType:
    monkeypatch.setenv("OPENMINIS_BRIDGE_HOME", str(state_home))
    monkeypatch.syspath_prepend(str(ASSET_ROOT))
    for name in tuple(sys.modules):
        if name.startswith("openminis_bridge_control"):
            del sys.modules[name]
    return importlib.import_module("openminis_bridge_control_core")


def test_every_runtime_asset_compiles() -> None:
    # Given / When / Then
    for path in (*RUNTIME_SOURCES, ASSET_ROOT / "installer_template.py"):
        compile(path.read_bytes(), str(path), "exec")


def test_runtime_subprocesses_are_literal_shell_false_and_no_broad_kill() -> None:
    # Given
    calls: list[tuple[Path, ast.Call]] = []
    source = "\n".join(path.read_text() for path in RUNTIME_SOURCES)
    for path in RUNTIME_SOURCES:
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
    assert "killall" not in source
    assert "pkill" not in source
    assert "os.system" not in source
    assert "shell=True" not in source
    assert "android-shizuku-cli exec" not in source


def test_generated_installer_payload_and_manifest_verify_in_memory() -> None:
    # Given
    package = build_bridge_package(
        BridgeIdentity(
            phone_ipv4="100.64.1.20",
            trusted_mac_ipv4="100.64.1.30",
            port=43129,
        ),
        ASSET_ROOT,
    )
    module_name = "generated_installer_test"
    module = ModuleType(module_name)
    sys.modules[module_name] = module
    try:
        exec(compile(package.artifact, package.artifact_name, "exec"), module.__dict__)  # noqa: S102
        manifest = module.__dict__["_manifest"]()
        files = module.__dict__["_archive_files"](manifest)
    finally:
        del sys.modules[module_name]

    # Then
    assert set(files) == {
        "openminis_bridge_control.py",
        "openminis_bridge_control_lifecycle.py",
        "openminis_bridge_control_process.py",
        "openminis_bridge_control_core/__init__.py",
        "openminis_bridge_control_core/actions.py",
        "openminis_bridge_control_core/http_api.py",
        "openminis_bridge_control_core/network.py",
        "openminis_bridge_control_core/protocol.py",
        "openminis_bridge_control_core/requests.py",
    }
    assert all(hashlib.sha256(files[name]).hexdigest() == manifest[name][1] for name in files)


def test_private_network_config_is_canonical_and_digest_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    config = {
        "schema": 1,
        "phone_ipv4": "100.64.1.20",
        "trusted_mac_ipv4": "100.64.1.30",
        "port": 43129,
    }
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path = state / "bridge.json"
    path.write_bytes(encoded)
    path.chmod(0o600)
    core = _fresh_core(monkeypatch, state)
    digest = hashlib.sha256(encoded).hexdigest()

    # When
    network = core.load_network(digest)

    # Then
    assert network.phone_ipv4 == "100.64.1.20"
    assert network.trusted_mac_ipv4 == "100.64.1.30"
    assert network.port == 43129
    with pytest.raises(core.BridgeError, match="identity changed"):
        core.load_network("0" * 64)


def test_http_authorization_uses_exact_enrolled_peer_or_local_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    core = _fresh_core(monkeypatch, tmp_path / "state")
    http_api = importlib.import_module("openminis_bridge_control_core.http_api")
    actions = importlib.import_module("openminis_bridge_control_core.actions")
    network = core.BridgeNetwork("100.64.1.20", "100.64.1.30", 43129, "a" * 64)
    runtime = http_api.Runtime("b" * 64, network, actions.CommandRunner(None, None))

    # When / Then
    http_api.authorize_client("100.64.1.30", "", runtime)
    http_api.authorize_client("127.0.0.1", f"Bearer {'b' * 64}", runtime)
    with pytest.raises(core.BridgeError, match="not allowed"):
        http_api.authorize_client("100.64.1.31", "", runtime)
    with pytest.raises(core.BridgeError, match="bearer"):
        http_api.authorize_client("127.0.0.1", "", runtime)


def test_request_parser_exposes_only_fixed_actions_and_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    core = _fresh_core(monkeypatch, tmp_path / "state")
    requests = importlib.import_module("openminis_bridge_control_core.requests")

    # When
    health = requests.parse_request(b'{"action":"health"}')
    tap = requests.parse_request(b'{"action":"tap_text","args":{"text":"Settings"}}')

    # Then
    assert health.argv == ()
    assert tap.argv == ("tap", "text", "Settings", "--compact")
    with pytest.raises(core.BridgeError, match="not supported"):
        requests.parse_request(b'{"action":"exec","args":{"argv":["id"]}}')
