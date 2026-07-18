"""Production HTTP and WebSocket runtime access protocol contracts."""

from fastapi.testclient import TestClient

from api.cors_config import CorsConfiguration, load_cors_configuration
from api.runtime_access import RuntimeAccessPolicy, load_runtime_access_policy
from api.server import app


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
