"""Test API Key authentication middleware."""
import os
import pytest
from fastapi.testclient import TestClient


class TestAuthMiddleware:
    """Test X-API-Key middleware behavior."""

    def test_no_key_returns_401(self):
        """Request without X-API-Key header returns 401."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get("/api/files?path=/nonexistent")
        assert response.status_code == 401
        body = response.json()
        assert "API_SECRET" in body.get("detail", "")

    def test_wrong_key_returns_401(self):
        """Wrong API key returns 401."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get(
            "/api/files?path=/nonexistent",
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_correct_key_passes(self):
        """Correct API key passes through to endpoint logic."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.get(
            "/api/files?path=/nonexistent",
            headers={"X-API-Key": "test-key"},
        )
        # 404 not found (directory doesn't exist) — NOT 401
        assert response.status_code != 401

    def test_cors_preflight_bypasses_api_key_auth(self):
        """Browser preflight has no X-API-Key and must reach CORS middleware."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        response = client.options(
            "/api/task",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-api-key,content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_api_secret_not_set_warns_and_passes(self):
        """If API_SECRET is not in env, log warning and skip auth."""
        if "API_SECRET" in os.environ:
            del os.environ["API_SECRET"]
        from api.server import app
        client = TestClient(app)
        response = client.get("/api/files?path=/nonexistent")
        # Should not be 401 when auth is disabled
        assert response.status_code != 401

    def test_websocket_protected(self):
        """WebSocket connection without proper key is rejected."""
        os.environ["API_SECRET"] = "test-key"
        from api.server import app
        client = TestClient(app)
        with pytest.raises(Exception) as exc_info:
            with client.websocket_connect("/ws/test-thread"):
                pass
        # Connection should be refused (auth failure)
