from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def test_legacy_http_runtime_routes_are_removed(monkeypatch):
    monkeypatch.setenv("API_SECRET", "test-integration-key")
    client = TestClient(app)

    cases = [
        ("POST", "/api/task"),
        ("GET", "/api/tasks/thread-1"),
        ("GET", "/api/research/runs"),
        ("GET", "/api/research/runs/thread-1"),
        ("GET", "/api/telemetry/thread-1"),
        ("GET", "/api/token-usage/thread-1"),
        ("POST", "/api/upload"),
        ("GET", "/api/download"),
        ("GET", "/api/files"),
    ]

    for method, path in cases:
        response = client.request(method, path, headers=AUTH_HEADERS)
        assert response.status_code == 404, (method, path, response.text)


def test_canonical_run_routes_remain_available():
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/runs" in paths
    assert "/api/runs/{run_id}" in paths
    assert "/api/runs/{run_id}/result" in paths
    assert "/api/telemetry/runs/{run_id}" in paths
    assert "/api/token-usage/runs/{run_id}" in paths


def test_legacy_thread_websocket_route_is_removed():
    websocket_paths = {
        route.path for route in app.routes if isinstance(route, WebSocketRoute)
    }

    assert "/ws/runs/{run_id}" in websocket_paths
    assert "/ws/{thread_id}" not in websocket_paths
