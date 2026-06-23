from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.server import app
from api.evidence_verification_repository import finalize_verification_snapshot
from api.run_repository import get_run
from tests.unit.test_publication_repository import (
    _accept_verification,
    _publication_tables,
    _seed_talent_run,
)


AUTH = {"X-API-Key": "correct"}


@pytest.fixture
def seeded_run(tmp_path, monkeypatch):
    seeded = _seed_talent_run(tmp_path, migrate=True)
    monkeypatch.setenv("TASKS_DB_PATH", seeded.db_path)
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "true",
    )
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "true",
    )
    monkeypatch.setenv("API_SECRET", "correct")
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )
    app.state.evidence_verification_runtime_readiness = SimpleNamespace(
        ready=True,
        application_schema_ready=True,
        review_runtime_ready=True,
    )
    app.state.review_worker_task = SimpleNamespace(done=lambda: False)
    return seeded


def test_verification_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        raising=False,
    )
    monkeypatch.delenv("API_SECRET", raising=False)

    response = TestClient(app).get(
        "/api/evidence-verifications/health",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "evidence_verification_disabled"


def test_auth_precedes_invalid_identity_and_missing_resource(
    seeded_run,
):
    response = TestClient(app).get(
        "/api/runs/invalid$id/evidence/verifications",
        headers={"X-API-Key": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


def test_health_reports_schema_and_review_worker_readiness(seeded_run):
    response = TestClient(app).get(
        "/api/evidence-verifications/health",
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "feature_enabled": True,
        "worker_running": True,
        "application_schema_ready": True,
        "review_runtime_ready": True,
    }


def test_list_and_detail_hide_private_audit_fields(seeded_run):
    client = TestClient(app)

    listed = client.get(
        f"/api/runs/{seeded_run.run_id}/evidence/verifications",
        headers=AUTH,
    )
    detail = client.get(
        (
            f"/api/runs/{seeded_run.run_id}/evidence/"
            f"{seeded_run.evidence_id}/verification"
        ),
        headers=AUTH,
    )

    assert listed.status_code == detail.status_code == 200
    assert listed.json()["items"][0]["evidence_id"] == seeded_run.evidence_id
    assert detail.json()["effective"]["evidence_id"] == seeded_run.evidence_id
    encoded = listed.text + detail.text
    assert "actor_fingerprint" not in encoded
    assert "request_hash" not in encoded


def test_decision_route_stales_publication_and_returns_replay_state(
    seeded_run,
):
    body = {
        "verification_id": "verification-api-1",
        "evidence_fingerprint": seeded_run.evidence_fingerprint,
        "expected_revision": 0,
        "action": "verify",
        "confirm_source_match": True,
        "reason_code": None,
        "reason_note": None,
    }
    client = TestClient(app)
    url = (
        f"/api/runs/{seeded_run.run_id}/evidence/"
        f"{seeded_run.evidence_id}/verification-decisions"
    )

    first = client.post(url, headers=AUTH, json=body)
    second = client.post(url, headers=AUTH, json=body)

    assert first.status_code == second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert get_run(
        db_path=seeded_run.db_path,
        run_id=seeded_run.run_id,
    )["delivery_status"] == "review_required"


def test_finalize_rejects_stale_state_without_partial_rows(seeded_run):
    _accept_verification(seeded_run)
    state_version = get_run(
        db_path=seeded_run.db_path,
        run_id=seeded_run.run_id,
    )["state_version"]
    before = _publication_tables(seeded_run.db_path)

    response = TestClient(app).post(
        (
            f"/api/runs/{seeded_run.run_id}/evidence/"
            "verification-snapshots"
        ),
        headers=AUTH,
        json={"expected_state_version": state_version - 1},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_state_version"
    assert _publication_tables(seeded_run.db_path) == before


def test_finalize_returns_publication_and_review_identity(seeded_run):
    _accept_verification(seeded_run)
    state_version = get_run(
        db_path=seeded_run.db_path,
        run_id=seeded_run.run_id,
    )["state_version"]

    response = TestClient(app).post(
        (
            f"/api/runs/{seeded_run.run_id}/evidence/"
            "verification-snapshots"
        ),
        headers=AUTH,
        json={"expected_state_version": state_version},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert response.json()["review_id"].startswith("review_")
    assert response.json()["idempotent_replay"] is False


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    [
        ("packet", "publication_packet_state_invalid"),
        ("snapshot", "verification_snapshot_invalid"),
    ],
)
def test_finalize_maps_corrupt_persisted_state_to_bounded_json(
    seeded_run,
    corruption,
    expected_code,
):
    _accept_verification(seeded_run)
    state_version = get_run(
        db_path=seeded_run.db_path,
        run_id=seeded_run.run_id,
    )["state_version"]
    connection = sqlite3.connect(seeded_run.db_path)
    try:
        if corruption == "packet":
            with connection:
                connection.execute(
                    """
                    UPDATE research_packets_v2
                    SET packet_json = '{'
                    WHERE run_id = ?
                    """,
                    (seeded_run.run_id,),
                )
        else:
            snapshot = finalize_verification_snapshot(
                db_path=seeded_run.db_path,
                run_id=seeded_run.run_id,
            )
            with connection:
                connection.execute(
                    """
                    UPDATE evidence_verification_snapshots_v2
                    SET snapshot_json = '{'
                    WHERE snapshot_id = ?
                    """,
                    (snapshot.snapshot.snapshot_id,),
                )
    finally:
        connection.close()

    response = TestClient(app, raise_server_exceptions=False).post(
        (
            f"/api/runs/{seeded_run.run_id}/evidence/"
            "verification-snapshots"
        ),
        headers=AUTH,
        json={"expected_state_version": state_version},
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == expected_code
    assert "traceback" not in response.text.lower()
    assert seeded_run.db_path not in response.text
