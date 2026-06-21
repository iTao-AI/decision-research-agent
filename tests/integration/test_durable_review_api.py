import pytest
from fastapi.testclient import TestClient

from api.server import app
from api.review_repository import _connect
from tests.unit.test_review_repository import _required_review_run


def _url(run_id, review_id):
    return f"/api/runs/{run_id}/reviews/{review_id}/decisions"


def _detail_url(run_id, review_id):
    return f"/api/runs/{run_id}/reviews/{review_id}"


@pytest.fixture
def required_review_run(tmp_path, monkeypatch):
    fixture = _required_review_run(tmp_path, suffix="api")
    monkeypatch.setenv("TASKS_DB_PATH", fixture.db_path)
    return fixture


@pytest.fixture
def approve_request():
    return {
        "decision_id": "decision_approve",
        "review_revision": 1,
        "action": "approve",
        "expected_state_version": 2,
    }


@pytest.fixture
def auth(required_review_run, tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")
    monkeypatch.setenv("TASKS_DB_PATH", required_review_run.db_path)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "review-checkpoints.db"),
    )
    return {"X-API-Key": "correct"}


@pytest.fixture
def manual_recovery_run(required_review_run):
    connection = _connect(required_review_run.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE review_workflows_v2
                SET status = 'manual_recovery',
                    last_error_code = 'checkpoint_corrupt'
                WHERE workflow_id = ?
                """,
                (required_review_run.workflow_id,),
            )
    finally:
        connection.close()
    return required_review_run


def test_review_list_requires_strict_review_auth(required_review_run, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")
    monkeypatch.setenv("TASKS_DB_PATH", required_review_run.db_path)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        f"{required_review_run.db_path}.checkpoints",
    )

    response = TestClient(app).get("/api/reviews")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_review_list_returns_bounded_waiting_projection(
    required_review_run,
    auth,
):
    response = TestClient(app).get("/api/reviews", headers=auth)

    assert response.status_code == 200
    item = response.json()["reviews"][0]
    assert item["run_id"] == required_review_run.run_id
    assert item["workflow_status"] == "waiting_decision"
    assert "reason" not in item
    assert "checkpoint_thread_id" not in item


def test_review_detail_returns_bundle_and_hides_audit_internals(
    required_review_run,
    auth,
):
    response = TestClient(app).get(
        (
            f"/api/runs/{required_review_run.run_id}"
            f"/reviews/{required_review_run.review_id}"
        ),
        headers=auth,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_bundle"]["review_id"] == required_review_run.review_id
    encoded = response.text
    assert "actor_fingerprint" not in encoded
    assert "checkpoint_thread_id" not in encoded
    assert "lease_owner" not in encoded


def test_review_health_reports_running_worker(auth):
    with TestClient(app) as client:
        response = client.get("/api/reviews/health", headers=auth)

    assert response.status_code == 200
    assert response.json()["worker_running"] is True


def test_invalid_review_cursor_returns_actionable_422(auth):
    response = TestClient(app).get(
        "/api/reviews?cursor=not-valid",
        headers=auth,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_query"


def test_disable_then_reenable_preserves_review_state(
    required_review_run,
    auth,
    monkeypatch,
):
    detail_url = (
        f"/api/runs/{required_review_run.run_id}"
        f"/reviews/{required_review_run.review_id}"
    )
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    disabled = TestClient(app).get(detail_url, headers=auth)
    assert disabled.status_code == 404
    assert disabled.json()["code"] == "durable_hitl_disabled"

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    enabled = TestClient(app).get(detail_url, headers=auth)
    assert enabled.status_code == 200
    assert enabled.json()["workflow"]["status"] == "waiting_decision"


def test_manual_recovery_is_visible_without_force_mutation_route(
    manual_recovery_run,
    auth,
):
    response = TestClient(app).get(
        (
            f"/api/runs/{manual_recovery_run.run_id}"
            f"/reviews/{manual_recovery_run.review_id}"
        ),
        headers=auth,
    )

    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "manual_recovery"
    assert response.json()["operator_guidance"]["code"] == "checkpoint_corrupt"
    paths = app.openapi()["paths"]
    assert not any("force" in path for path in paths)


def test_decision_route_is_not_deprecated():
    operation = app.openapi()["paths"][
        "/api/runs/{run_id}/reviews/{review_id}/decisions"
    ]["post"]

    assert "deprecated" not in operation


def test_decision_route_documents_required_json_request_body():
    operation = app.openapi()["paths"][
        "/api/runs/{run_id}/reviews/{review_id}/decisions"
    ]["post"]

    assert operation["requestBody"] == {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"title": "Body"},
            },
        },
    }


@pytest.mark.parametrize(
    ("identity_field", "invalid_identity"),
    [
        ("run_id", "r" * 129),
        ("run_id", "invalid$run"),
        ("review_id", "r" * 129),
        ("review_id", "invalid$review"),
    ],
)
def test_review_detail_rejects_unbounded_identity_after_auth(
    required_review_run,
    auth,
    identity_field,
    invalid_identity,
):
    identities = {
        "run_id": required_review_run.run_id,
        "review_id": required_review_run.review_id,
    }
    identities[identity_field] = invalid_identity

    response = TestClient(app).get(
        _detail_url(**identities),
        headers=auth,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_identity"
    assert "errors" not in response.json()


@pytest.mark.parametrize(
    ("identity_field", "invalid_identity"),
    [
        ("run_id", "r" * 129),
        ("run_id", "invalid$run"),
        ("review_id", "r" * 129),
        ("review_id", "invalid$review"),
    ],
)
def test_review_decision_rejects_unbounded_identity_before_body(
    required_review_run,
    auth,
    identity_field,
    invalid_identity,
):
    identities = {
        "run_id": required_review_run.run_id,
        "review_id": required_review_run.review_id,
    }
    identities[identity_field] = invalid_identity

    response = TestClient(app).post(
        _url(**identities),
        content="{",
        headers={**auth, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_identity"
    assert "errors" not in response.json()


@pytest.mark.parametrize("route_kind", ["detail", "decision"])
@pytest.mark.parametrize(
    ("auth_state", "expected_status", "expected_code"),
    [
        ("disabled", 404, "durable_hitl_disabled"),
        ("missing_secret", 503, "review_auth_not_configured"),
        ("wrong_key", 401, "invalid_api_key"),
    ],
)
def test_review_auth_precedes_invalid_identity(
    required_review_run,
    monkeypatch,
    route_kind,
    auth_state,
    expected_status,
    expected_code,
):
    if auth_state == "disabled":
        monkeypatch.setenv(
            "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
            "false",
        )
        monkeypatch.delenv("API_SECRET", raising=False)
        headers = {}
    elif auth_state == "missing_secret":
        monkeypatch.setenv(
            "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
            "true",
        )
        monkeypatch.delenv("API_SECRET", raising=False)
        headers = {}
    else:
        monkeypatch.setenv(
            "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
            "true",
        )
        monkeypatch.setenv("API_SECRET", "correct")
        headers = {"X-API-Key": "wrong"}

    run_id = "invalid$run"
    review_id = required_review_run.review_id
    client = TestClient(app)
    if route_kind == "detail":
        response = client.get(
            _detail_url(run_id, review_id),
            headers=headers,
        )
    else:
        response = client.post(
            _url(run_id, review_id),
            content="{",
            headers={**headers, "Content-Type": "application/json"},
        )

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


def test_decision_api_is_disabled_by_default(
    required_review_run,
    approve_request,
    monkeypatch,
):
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        raising=False,
    )
    monkeypatch.delenv("API_SECRET", raising=False)

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "durable_hitl_disabled"


def test_enabled_decision_api_fails_closed_without_api_secret(
    required_review_run,
    approve_request,
    monkeypatch,
):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "true",
    )
    monkeypatch.delenv("API_SECRET", raising=False)

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
    )

    assert response.status_code == 503
    assert response.json()["code"] == "review_auth_not_configured"


def test_flag_and_auth_are_checked_before_body_validation(
    required_review_run,
    monkeypatch,
):
    url = _url(required_review_run.run_id, required_review_run.review_id)
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        raising=False,
    )
    monkeypatch.delenv("API_SECRET", raising=False)

    disabled = TestClient(app).post(url, json={})
    assert disabled.status_code == 404
    assert disabled.json()["code"] == "durable_hitl_disabled"

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    unconfigured = TestClient(app).post(url, json={})
    assert unconfigured.status_code == 503
    assert unconfigured.json()["code"] == "review_auth_not_configured"


def test_disabled_review_auth_precedes_malformed_json(
    required_review_run,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.delenv("API_SECRET", raising=False)

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "durable_hitl_disabled"


def test_missing_review_secret_precedes_malformed_json(
    required_review_run,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "review_auth_not_configured"


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "application/json"},
        {"Content-Type": "application/json", "X-API-Key": "wrong"},
    ],
)
def test_invalid_review_key_precedes_malformed_json(
    required_review_run,
    monkeypatch,
    headers,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content="{",
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_wrong_key_is_rejected(
    required_review_run,
    approve_request,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "correct")

    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
        headers={"X-API-Key": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_authenticated_invalid_body_returns_bounded_contract_error(
    required_review_run,
    auth,
):
    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json={},
        headers=auth,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_decision"
    assert "errors" not in response.json()


def test_authenticated_malformed_json_returns_bounded_contract_error(
    required_review_run,
    auth,
):
    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content="{",
        headers={**auth, "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_decision"
    assert "errors" not in response.json()


def test_authenticated_non_json_content_type_is_rejected_without_decision(
    required_review_run,
    auth,
):
    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content=(
            '{"decision_id":"decision_approve","review_revision":1,'
            '"action":"approve","expected_state_version":2}'
        ),
        headers={**auth, "Content-Type": "text/plain"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_review_decision"
    connection = _connect(required_review_run.db_path)
    try:
        decision = connection.execute(
            "SELECT decision_id FROM review_decisions_v2 WHERE run_id = ?",
            (required_review_run.run_id,),
        ).fetchone()
    finally:
        connection.close()
    assert decision is None


def test_authenticated_json_without_content_type_is_accepted(
    required_review_run,
    auth,
):
    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content=(
            '{"decision_id":"decision_approve","review_revision":1,'
            '"action":"approve","expected_state_version":2}'
        ),
        headers=auth,
    )

    assert response.status_code == 202
    assert response.json()["decision_id"] == "decision_approve"


def test_authenticated_structured_json_content_type_is_accepted(
    required_review_run,
    auth,
):
    response = TestClient(app).post(
        _url(required_review_run.run_id, required_review_run.review_id),
        content=(
            '{"decision_id":"decision_approve","review_revision":1,'
            '"action":"approve","expected_state_version":2}'
        ),
        headers={
            **auth,
            "Content-Type": "application/problem+json; charset=utf-8",
        },
    )

    assert response.status_code == 202
    assert response.json()["decision_id"] == "decision_approve"


def test_decision_api_accepts_and_replays_same_request(
    required_review_run,
    approve_request,
    auth,
):
    client = TestClient(app)
    first = client.post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
        headers=auth,
    )
    second = client.post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
        headers=auth,
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True


def test_conflicting_decision_returns_actionable_409(
    required_review_run,
    approve_request,
    auth,
):
    client = TestClient(app)
    first = client.post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=approve_request,
        headers=auth,
    )
    assert first.status_code == 202
    conflicting = {
        **approve_request,
        "decision_id": "decision_conflicting",
        "action": "reject",
        "reason": "Evidence boundary was not accepted.",
    }

    response = client.post(
        _url(required_review_run.run_id, required_review_run.review_id),
        json=conflicting,
        headers=auth,
    )

    assert response.status_code == 409
    body = response.json()
    request_id = body.pop("request_id")
    assert request_id.startswith("request_")
    assert body == {
        "code": "review_already_decided",
        "problem": "This review revision already has an accepted decision.",
        "cause": "A conflicting decision was submitted.",
        "fix": "Fetch the run and use the persisted decision result.",
        "retryable": False,
        "run_id": required_review_run.run_id,
    }
