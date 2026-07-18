"""Production HTTP and WebSocket runtime access protocol contracts."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.cors_config import CorsConfiguration, load_cors_configuration
from api.runtime_access import RuntimeAccessPolicy, load_runtime_access_policy
from api.server import app


def _set_runtime(monkeypatch, environ: dict[str, str]) -> None:
    policy = load_runtime_access_policy(environ)
    monkeypatch.setattr(app.state, "runtime_access_policy", policy)
    monkeypatch.setattr(
        app.state,
        "cors_configuration",
        load_cors_configuration(access_policy=policy, environ=environ),
    )


def _client(*, peer: str = "127.0.0.1") -> TestClient:
    return TestClient(
        app,
        base_url="http://127.0.0.1",
        client=(peer, 50000),
        follow_redirects=False,
    )


def test_application_owns_one_frozen_runtime_configuration():
    assert isinstance(app.state.runtime_access_policy, RuntimeAccessPolicy)
    assert isinstance(app.state.cors_configuration, CorsConfiguration)


def test_real_application_rejects_remote_empty_secret_before_route(monkeypatch):
    policy = load_runtime_access_policy({})
    monkeypatch.setattr(app.state, "runtime_access_policy", policy)
    monkeypatch.setattr(
        app.state,
        "cors_configuration",
        load_cors_configuration(access_policy=policy, environ={}),
    )
    response = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("192.0.2.10", 50000),
        follow_redirects=False,
    ).get("/api/runs/nonexistent")
    assert response.status_code == 503
    assert response.json()["code"] == "api_auth_not_configured"


@pytest.mark.parametrize(
    ("environ", "peer", "url", "headers", "close_code", "reason"),
    [
        (
            {"API_SECRET": "test-secret"},
            "127.0.0.1",
            "/ws/runs/run_1",
            {},
            4001,
            "api_key_invalid",
        ),
        (
            {"API_SECRET": "test-secret"},
            "127.0.0.1",
            "/ws/runs/run_1?api_key=do-not-copy",
            {"X-API-Key": "test-secret"},
            1008,
            "query_credential_rejected",
        ),
        (
            {
                "API_SECRET": "test-secret",
                "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN": "https://allowed.example",
            },
            "127.0.0.1",
            "/ws/runs/run_1",
            {"X-API-Key": "test-secret", "Origin": "https://wrong.example"},
            1008,
            "origin_not_allowed",
        ),
        ({}, "192.0.2.10", "/ws/runs/run_1", {}, 1008, "api_auth_not_configured"),
        ({}, "127.0.0.1", "/ws/runs/run_1", {"Host": "localhost"}, 1008, "local_authority_required"),
        ({}, "127.0.0.1", "/ws/runs/run_1", {"Forwarded": "for=192.0.2.1"}, 1008, "forwarded_request_rejected"),
    ],
)
def test_websocket_denials_precede_identity_lookup_and_connection(
    monkeypatch,
    environ,
    peer,
    url,
    headers,
    close_code,
    reason,
):
    import api.server as server

    _set_runtime(monkeypatch, environ)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("identity_or_database_reached_before_access")

    async def unexpected_connect(*_args, **_kwargs):
        raise AssertionError("connection_owned_before_access")

    monkeypatch.setattr(server, "validate_thread_id", unexpected)
    monkeypatch.setattr(server, "get_run", unexpected)
    monkeypatch.setattr(server.manager, "connect_run", unexpected_connect)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with _client(peer=peer).websocket_connect(url, headers=headers):
            pass

    assert exc_info.value.code == close_code
    assert exc_info.value.reason == reason
    for supplied in ("test-secret", "do-not-copy", "wrong.example", "192.0.2.1", "localhost"):
        assert supplied not in exc_info.value.reason


def test_websocket_absent_origin_reaches_run_identity_after_access(monkeypatch):
    import api.server as server

    _set_runtime(monkeypatch, {"API_SECRET": "configured"})
    observed = []

    def invalid_run_id(value):
        observed.append(value)
        raise ValueError("invalid")

    monkeypatch.setattr(server, "validate_thread_id", invalid_run_id)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with _client().websocket_connect(
            "/ws/runs/invalid",
            headers={"X-API-Key": "configured"},
        ):
            pass

    assert observed == ["invalid"]
    assert exc_info.value.reason == "Invalid run_id"


def test_websocket_missing_run_does_not_take_connection_ownership(monkeypatch):
    import api.server as server

    _set_runtime(monkeypatch, {"API_SECRET": "configured"})
    monkeypatch.setattr(server, "validate_thread_id", lambda value: value)
    monkeypatch.setattr(server, "get_run", lambda *, run_id: None)

    async def unexpected_connect(*_args, **_kwargs):
        raise AssertionError("connection_owned_for_missing_run")

    monkeypatch.setattr(server.manager, "connect_run", unexpected_connect)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with _client().websocket_connect(
            "/ws/runs/missing",
            headers={"X-API-Key": "configured"},
        ):
            pass
    assert exc_info.value.reason == "ResearchRun not found"
