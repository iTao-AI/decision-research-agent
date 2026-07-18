from fastapi.testclient import TestClient

from api.runtime_access import load_runtime_access_policy


def test_health_endpoint_bypasses_api_key_auth():
    from api.server import app

    app.state.runtime_access_policy = load_runtime_access_policy(
        {"API_SECRET": "test-key"}
    )

    response = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "decision-research-agent"}
