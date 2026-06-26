import os
import hashlib

from fastapi.testclient import TestClient

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    os.environ["API_SECRET"] = "test-integration-key"
    return TestClient(app)


def _artifact(
    *,
    artifact_id="research-report.md",
    kind="research_report_markdown",
    content="# Report",
):
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "media_type": "text/markdown",
        "content": content,
        "content_hash": content_hash,
    }


def test_result_unknown_run_returns_stable_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/runs/run_missing/result", headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"


def test_result_pending_run_returns_run_not_terminal(tmp_path, monkeypatch):
    from api.run_repository import create_run

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_not_terminal"


def test_result_failed_run_returns_run_failed(tmp_path, monkeypatch):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="failed",
        delivery_status="failed",
        evidence_entries=[],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_failed"


def test_result_review_required_run_returns_run_review_required(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
    )
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        evidence_entries=[],
        artifacts=[_artifact(artifact_id="decision-brief.md", kind="decision_brief_markdown")],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_review_required"


def test_result_blocked_run_returns_run_delivery_blocked(tmp_path, monkeypatch):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="resolved",
        delivery_status="blocked",
        evidence_entries=[],
        artifacts=[_artifact()],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_delivery_blocked"


def test_result_ready_run_with_missing_artifact_returns_unavailable(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_result_unavailable"


def test_result_ready_generic_returns_bounded_artifact_payload(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[_artifact(content="# Report\nNo /Users/private/path")],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == created["run_id"]
    assert body["execution_status"] == "completed"
    assert body["delivery_status"] == "ready"
    assert body["artifact"] == {
        "artifact_id": "research-report.md",
        "kind": "research_report_markdown",
        "media_type": "text/markdown",
        "content": "# Report\nNo /Users/private/path",
        "content_hash": hashlib.sha256(
            "# Report\nNo /Users/private/path".encode("utf-8")
        ).hexdigest(),
    }
    serialized = str(body)
    assert "tasks.db" not in serialized
    assert "Traceback" not in serialized
    assert "checkpoint" not in serialized.lower()


def test_result_ready_talent_without_publication_returns_decision_brief_markdown(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run, finalize_run_transaction

    client = _client(tmp_path, monkeypatch)
    created = create_run(
        thread_id="thread-1",
        query="query",
        profile_id="talent-hiring-signal",
    )
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        review_status="not_required",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[
            _artifact(
                artifact_id="decision-brief.json",
                kind="decision_brief_json",
                content="{}",
            ),
            _artifact(
                artifact_id="decision-brief.md",
                kind="decision_brief_markdown",
                content="# Decision Brief",
            ),
        ],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["artifact"]["artifact_id"] == "decision-brief.md"
    assert response.json()["artifact"]["content"] == "# Decision Brief"
