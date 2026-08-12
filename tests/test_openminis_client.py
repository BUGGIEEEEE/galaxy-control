from __future__ import annotations

from pathlib import Path

import pytest

from galaxy_profile import DeviceProfile, write_profile
from openminis_client import ClientError, parse_response, read_token
from openminis_protocol import Action


def profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DeviceProfile:
    monkeypatch.setenv("GALAXY_CONTROL_HOME", str(tmp_path / "support"))
    value = DeviceProfile(
        schema=1,
        physical_serial="DEMO123456",
        expected_model="SM_S921B",
        tailscale_ipv4="100.64.1.20",
        openminis_port=43129,
        steady_adb_enabled=False,
    )
    _ = write_profile(value)
    return value


def test_response_accepts_matching_success_action() -> None:
    # Given
    content = b'{"ok":true,"action":"health","result":{"status":"ok"}}'

    # When
    response = parse_response(content, Action.HEALTH)

    # Then
    assert response.result == {
        "status": "ok",
        "route": {
            "controller": "openminis",
            "transport": "tailscale_http",
            "role": "observe",
            "verification_required": False,
            "verify_with": [],
        },
    }


def test_response_rejects_mismatched_action() -> None:
    # Given
    content = b'{"ok":true,"action":"ui_info","result":{}}'

    # When / Then
    with pytest.raises(ClientError, match="action"):
        parse_response(content, Action.HEALTH)


def test_response_rejects_duplicate_json_key() -> None:
    # Given / When / Then
    with pytest.raises(ClientError, match="JSON"):
        parse_response(b'{"ok":true,"ok":false}', Action.HEALTH)


def test_token_is_read_only_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    token = "a" * 64
    monkeypatch.setenv("OPENMINIS_BRIDGE_TOKEN", token)

    # When
    secret = read_token()

    # Then
    assert secret is not None
    assert secret.get_secret_value() == token


def test_invalid_environment_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("OPENMINIS_BRIDGE_TOKEN", "not-a-token")

    # When / Then
    with pytest.raises(ClientError, match="token"):
        read_token()


def test_openminis_action_payload_identifies_route_and_verification_need() -> None:
    # Given
    response = parse_response(
        b'{"ok":true,"action":"tap_text","result":{"performed":true}}',
        Action.TAP_TEXT,
    )

    # When
    payload = response.model_dump(mode="json")

    # Then
    assert payload["result"]["route"] == {
        "controller": "openminis",
        "transport": "tailscale_http",
        "role": "act",
        "verification_required": True,
        "verify_with": ["openminis", "adb"],
    }
    assert payload["result"]["route"]["verify_with"] == ["openminis", "adb"]


@pytest.mark.parametrize("result_json", ["[]", '"text"', "1", "null"])
def test_success_response_rejects_non_object_result(result_json: str) -> None:
    # Given
    content = f'{{"ok":true,"action":"health","result":{result_json}}}'.encode()

    # When / Then
    with pytest.raises(ClientError) as captured:
        parse_response(content, Action.HEALTH)
    assert captured.value.code == "invalid_response"


def test_success_response_rejects_bridge_owned_route_field() -> None:
    # Given
    content = b'{"ok":true,"action":"health","result":{"route":"untrusted"}}'

    # When / Then
    with pytest.raises(ClientError) as captured:
        parse_response(content, Action.HEALTH)
    assert captured.value.code == "invalid_response"
