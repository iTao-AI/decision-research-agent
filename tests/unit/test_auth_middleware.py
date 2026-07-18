"""Production runtime access middleware contracts."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.cors_config import load_cors_configuration
from api.runtime_access import load_runtime_access_policy
from api.server import RuntimeAccessMiddleware, _emit_runtime_access_warning_once


def _app(*, secret: str | None = None, origin: str | None = None) -> FastAPI:
    app = FastAPI()
    environ = {} if secret is None else {"API_SECRET": secret}
    if origin is not None:
        environ["DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN"] = origin
    policy = load_runtime_access_policy(environ)
    app.state.runtime_access_policy = policy
    app.state.cors_configuration = load_cors_configuration(
        access_policy=policy,
        environ=environ,
    )
    app.add_middleware(RuntimeAccessMiddleware)

    @app.get("/protected")
    async def protected():
        return {"reached": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/reviews")
    async def reviews():
        return {"feature_gate": True}

    @app.options("/protected")
    async def preflight():
        return {"preflight": True}

    return app


def _client(app: FastAPI, *, peer: str = "127.0.0.1", base_url: str = "http://127.0.0.1"):
    return TestClient(
        app,
        base_url=base_url,
        client=(peer, 50000),
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    ("peer", "headers"),
    [("127.0.0.1", {}), ("::1", {"Host": "[::1]"})],
)
def test_empty_secret_allows_explicit_loopback(peer: str, headers: dict[str, str]):
    response = _client(_app(), peer=peer).get("/protected", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_remote_empty_secret_returns_bounded_503():
    response = _client(_app(), peer="192.0.2.10").get("/protected")
    assert response.status_code == 503
    assert response.json() == {
        "code": "api_auth_not_configured",
        "problem": "The service is not configured for remote unauthenticated access.",
        "cause": "The direct client is not an explicit loopback peer.",
        "fix": "Use the loopback source runtime or configure X-API-Key.",
        "retryable": False,
    }


@pytest.mark.parametrize(
    ("headers", "code", "supplied"),
    [
        ({"Host": "localhost"}, "local_authority_required", "localhost"),
        ({"Host": "example.com"}, "local_authority_required", "example.com"),
        ({"X-Forwarded-For": ""}, "forwarded_request_rejected", None),
        ({"Forwarded": "for=192.0.2.1"}, "forwarded_request_rejected", "192.0.2.1"),
    ],
)
def test_empty_secret_rejects_unsafe_authority_or_forwarding(headers, code, supplied):
    response = _client(_app()).get("/protected", headers=headers)
    assert response.status_code == 503
    assert response.json()["code"] == code
    if supplied is not None:
        assert supplied not in response.text


def test_configured_secret_returns_tool_client_compatible_error():
    response = _client(_app(secret="configured")).get(
        "/protected",
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "code": "api_key_invalid",
        "problem": "The service credential is invalid.",
        "cause": "X-API-Key did not match the configured service credential.",
        "fix": "Provide the configured X-API-Key.",
        "retryable": False,
    }
    assert "wrong" not in response.text


def test_configured_utf8_secret_allows_local_and_remote_peer():
    app = _app(secret="密钥")
    for peer in ("127.0.0.1", "192.0.2.10"):
        response = _client(app, peer=peer).get(
            "/protected",
            headers={"X-API-Key": "密钥".encode("utf-8")},
        )
        assert response.status_code == 200


def test_disallowed_origin_returns_bounded_403_before_route():
    response = _client(
        _app(secret="configured", origin="https://allowed.example")
    ).get(
        "/protected",
        headers={"Origin": "https://wrong.example", "X-API-Key": "configured"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"
    assert "wrong.example" not in response.text


@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json", "/redoc"])
def test_public_paths_bypass_runtime_access(path: str):
    response = _client(_app(secret="configured")).get(path)
    assert response.status_code != 401


def test_options_and_feature_owned_path_bypass_general_access():
    app = _app(secret="configured")
    assert _client(app).options("/protected").status_code == 200
    response = _client(app).get("/api/reviews")
    assert response.status_code == 200
    assert response.json() == {"feature_gate": True}


def test_empty_secret_requests_do_not_emit_per_request_warning(caplog):
    caplog.set_level(logging.WARNING)
    client = _client(_app())
    client.get("/protected")
    client.get("/protected")
    assert "loopback_only" not in caplog.text


def test_empty_secret_startup_warning_is_emitted_once(caplog):
    test_app = SimpleNamespace(
        state=SimpleNamespace(
            runtime_access_policy=load_runtime_access_policy({}),
            runtime_access_warning_emitted=False,
        )
    )
    caplog.set_level(logging.WARNING)

    _emit_runtime_access_warning_once(test_app)
    _emit_runtime_access_warning_once(test_app)

    assert caplog.text.count("loopback_only") == 1
    assert test_app.state.runtime_access_warning_emitted is True
