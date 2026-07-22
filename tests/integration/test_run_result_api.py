import os
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

from fastapi.testclient import TestClient
import pytest

from agent.harness_contracts import ReportCandidate
from agent.run_result import ExecutionOutcome
from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}
pytestmark = pytest.mark.usefixtures("authenticated_runtime_access")


@dataclass(frozen=True)
class SeededRun:
    db_path: Path
    run_id: str
    segment_id: str


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_DB_PATH", str(tmp_path / "tasks.db"))
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


def _seed_ready_generic(
    tmp_path,
    *,
    kind="research_report_markdown",
    content="# Report",
):
    from api.run_repository import create_run, finalize_run_transaction

    db_path = tmp_path / "tasks.db"
    created = create_run(
        db_path=str(db_path),
        thread_id="thread-1",
        query="query",
    )
    assert finalize_run_transaction(
        db_path=str(db_path),
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[_artifact(kind=kind, content=content)],
    )
    return SeededRun(
        db_path=db_path,
        run_id=created["run_id"],
        segment_id=created["segment_id"],
    )


def test_run_delivery_snapshot_contains_only_resolver_inputs(tmp_path):
    from api.run_repository import get_run_delivery_snapshot

    seeded = _seed_ready_generic(tmp_path, content="# Decision Brief")
    snapshot = get_run_delivery_snapshot(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert set(snapshot) == {
        "run_id",
        "profile_id",
        "execution_status",
        "delivery_status",
        "current_artifact_ids",
        "artifacts",
    }
    assert snapshot["current_artifact_ids"] == ()
    assert snapshot["artifacts"][0]["content"] == "# Decision Brief"


def test_run_delivery_snapshot_preserves_talent_artifact_rows(tmp_path):
    from api.run_repository import (
        create_run,
        finalize_run_transaction,
        get_run_delivery_snapshot,
    )

    db_path = tmp_path / "tasks.db"
    created = create_run(
        db_path=str(db_path),
        thread_id="thread-talent",
        query="query",
        profile_id="talent-hiring-signal",
    )
    assert finalize_run_transaction(
        db_path=str(db_path),
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[
            _artifact(
                artifact_id="decision-brief.md",
                kind="decision_brief_markdown",
                content="# Decision Brief",
            )
        ],
    )

    snapshot = get_run_delivery_snapshot(
        db_path=str(db_path),
        run_id=created["run_id"],
    )

    assert snapshot["profile_id"] == "talent-hiring-signal"
    assert snapshot["current_artifact_ids"] == ()
    assert snapshot["artifacts"][0]["artifact_id"] == "decision-brief.md"
    assert snapshot["artifacts"][0]["content"] == "# Decision Brief"


def test_run_delivery_snapshot_unknown_run_returns_none(tmp_path):
    from api.run_repository import get_run_delivery_snapshot

    assert get_run_delivery_snapshot(
        db_path=str(tmp_path / "tasks.db"),
        run_id="run_missing",
    ) is None


def test_run_delivery_snapshot_uses_one_sqlite_read_snapshot(
    tmp_path,
    monkeypatch,
):
    import api.run_repository as repository

    seeded = _seed_ready_generic(tmp_path, content="# Original")
    real_connect = repository._connect
    interleaved = False

    class InterleavingConnection:
        def __init__(self, connection):
            self._connection = connection

        def execute(self, statement, parameters=()):
            nonlocal interleaved
            if "FROM run_artifacts_v2" in statement and not interleaved:
                interleaved = True
                writer = real_connect(str(seeded.db_path))
                try:
                    with writer:
                        writer.execute(
                            """
                            UPDATE research_runs_v2
                            SET delivery_status = 'blocked', state_version = state_version + 1
                            WHERE run_id = ?
                            """,
                            (seeded.run_id,),
                        )
                        writer.execute(
                            """
                            UPDATE run_artifacts_v2
                            SET content = ?, content_hash = ?
                            WHERE run_id = ? AND artifact_id = ?
                            """,
                            (
                                "# Replacement",
                                hashlib.sha256(b"# Replacement").hexdigest(),
                                seeded.run_id,
                                "research-report.md",
                            ),
                        )
                finally:
                    writer.close()
            return self._connection.execute(statement, parameters)

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._connection.__exit__(exc_type, exc_value, traceback)

        def commit(self):
            return self._connection.commit()

        def rollback(self):
            return self._connection.rollback()

        def close(self):
            return self._connection.close()

    monkeypatch.setattr(
        repository,
        "_connect",
        lambda db_path=None: InterleavingConnection(real_connect(db_path)),
    )
    first = repository.get_run_delivery_snapshot(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )
    monkeypatch.setattr(repository, "_connect", real_connect)
    second = repository.get_run_delivery_snapshot(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert first["delivery_status"] == "ready"
    assert first["artifacts"][0]["content"] == "# Original"
    assert second["delivery_status"] == "blocked"
    assert second["artifacts"][0]["content"] == "# Replacement"


def test_resolver_uses_snapshot_artifact_without_a_second_read(
    tmp_path,
    monkeypatch,
):
    import api.run_result_service as service

    seeded = _seed_ready_generic(tmp_path, content="# Snapshot Result")

    def reject_raw_read(**kwargs):
        raise AssertionError(f"unexpected raw artifact read: {kwargs}")

    monkeypatch.setattr(service, "get_artifact", reject_raw_read, raising=False)

    result = service.resolve_run_result(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert result.artifact["content"] == "# Snapshot Result"


def test_ready_fallback_is_a_legal_canonical_result(tmp_path):
    from api.run_result_service import resolve_run_result

    seeded = _seed_ready_generic(
        tmp_path,
        kind="research_report_fallback_markdown",
        content="# Fallback Report\n\nBounded result.",
    )

    result = resolve_run_result(
        db_path=str(seeded.db_path),
        run_id=seeded.run_id,
    )

    assert result.artifact["kind"] == "research_report_fallback_markdown"
    assert result.artifact["content"] == "# Fallback Report\n\nBounded result."


def test_resolver_fails_closed_on_corrupt_delivery_snapshot(tmp_path):
    from api.run_result_service import RunResultUnavailable, resolve_run_result

    seeded = _seed_ready_generic(tmp_path)
    connection = sqlite3.connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE run_publications_v2 (
                    run_id TEXT NOT NULL,
                    is_current INTEGER NOT NULL,
                    artifact_ids_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO run_publications_v2(
                    run_id, is_current, artifact_ids_json
                ) VALUES (?, 1, ?)
                """,
                (seeded.run_id, "not-json"),
            )
    finally:
        connection.close()

    with pytest.raises(RunResultUnavailable) as raised:
        resolve_run_result(
            db_path=str(seeded.db_path),
            run_id=seeded.run_id,
        )

    assert raised.value.code == "run_result_unavailable"


@pytest.mark.parametrize(
    ("content", "content_hash"),
    [
        ("", hashlib.sha256(b"").hexdigest()),
        ("x" * (1024 * 1024 + 1), hashlib.sha256(b"oversized").hexdigest()),
        ("host=/Users/private/tasks.db", hashlib.sha256(b"unsafe").hexdigest()),
        ("# Tampered", hashlib.sha256(b"# Original").hexdigest()),
    ],
    ids=("empty", "oversized", "unsafe", "hash-mismatch"),
)
def test_invalid_artifact_generic_content_fails_closed(
    tmp_path,
    content,
    content_hash,
):
    from api.run_result_service import RunResultUnavailable, resolve_run_result

    seeded = _seed_ready_generic(tmp_path)
    connection = sqlite3.connect(seeded.db_path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE run_artifacts_v2
                SET content = ?, content_hash = ?
                WHERE run_id = ? AND artifact_id = 'research-report.md'
                """,
                (content, content_hash, seeded.run_id),
            )
    finally:
        connection.close()

    with pytest.raises(RunResultUnavailable) as raised:
        resolve_run_result(
            db_path=str(seeded.db_path),
            run_id=seeded.run_id,
        )

    assert raised.value.code == "run_result_unavailable"


@pytest.mark.parametrize(
    ("content", "content_hash"),
    [
        ("", "a" * 64),
        ("x" * (1024 * 1024 + 1), "a" * 64),
        ("# Decision Brief", "not-a-valid-hash"),
    ],
    ids=("empty", "oversized", "malformed-hash"),
)
def test_invalid_artifact_talent_content_fails_closed(
    tmp_path,
    content,
    content_hash,
):
    from api.run_repository import create_run, finalize_run_transaction
    from api.run_result_service import RunResultUnavailable, resolve_run_result

    db_path = tmp_path / "tasks.db"
    created = create_run(
        db_path=str(db_path),
        thread_id="thread-talent",
        query="query",
        profile_id="talent-hiring-signal",
    )
    assert finalize_run_transaction(
        db_path=str(db_path),
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[
            {
                "artifact_id": "decision-brief.md",
                "kind": "decision_brief_markdown",
                "media_type": "text/markdown",
                "content": content,
                "content_hash": content_hash,
            }
        ],
    )

    with pytest.raises(RunResultUnavailable) as raised:
        resolve_run_result(db_path=str(db_path), run_id=created["run_id"])

    assert raised.value.code == "run_result_unavailable"


def _outcome(**kwargs):
    values = {
        "thread_id": "thread-1",
        "query": "query",
        "session_dir": PurePosixPath("/workspace/session"),
        "run_id": "run_1",
        "segment_id": "run_1_seg_000",
        "last_agent_text": "",
        "diagnostics": [],
    }
    values.update(kwargs)
    return ExecutionOutcome(**values)


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
    from api.run_failure_cause_models import RunFailureCauseWrite
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
        failure_cause=RunFailureCauseWrite(
            phase="execution",
            code="execution_error",
        ),
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_failed"
    assert response.content == json.dumps(
        {
            "code": "run_failed",
            "problem": "The ResearchRun failed and has no deliverable result.",
            "fix": (
                "Inspect the bounded run projection and start a new run if needed."
            ),
            "retryable": True,
            "run_id": created["run_id"],
        },
        separators=(",", ":"),
    ).encode("utf-8")


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
        artifacts=[_artifact(content="# Report\nNo private path")],
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
        "content": "# Report\nNo private path",
        "content_hash": hashlib.sha256(
            "# Report\nNo private path".encode("utf-8")
        ).hexdigest(),
    }
    serialized = str(body)
    assert "tasks.db" not in serialized
    assert "Traceback" not in serialized
    assert "checkpoint" not in serialized.lower()


def test_result_ready_generic_rejects_unsafe_persisted_artifact(
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
        artifacts=[
            _artifact(
                content=(
                    "# Report\n"
                    "host=/Users/private/project/tasks.db\n"
                    "Traceback (most recent call last):\n"
                    "checkpoint_thread_id=thread-1"
                ),
            )
        ],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_result_unavailable"


def test_result_ready_generic_accepts_builder_sanitized_artifact(
    tmp_path,
    monkeypatch,
):
    from api.run_repository import create_run, finalize_run_transaction
    from api.run_result_service import build_generic_result_artifact

    client = _client(tmp_path, monkeypatch)
    created = create_run(thread_id="thread-1", query="query")
    artifact = build_generic_result_artifact(
        _outcome(
            run_id=created["run_id"],
            segment_id=created["segment_id"],
            report_candidate=ReportCandidate(
                path=PurePosixPath("/workspace/research-report.md"),
                content=(
                    "# Report\n"
                    "Useful finding.\n"
                    "host=/Users/private/project/tasks.db\n"
                    "Traceback (most recent call last):\n"
                    "checkpoint_thread_id=thread-1"
                ),
            ),
        )
    )
    finalize_run_transaction(
        run_id=created["run_id"],
        segment_id=created["segment_id"],
        expected_state_version=0,
        allowed_previous_statuses={"pending"},
        execution_status="completed",
        delivery_status="ready",
        evidence_entries=[],
        artifacts=[artifact],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert "Useful finding." in body["artifact"]["content"]
    assert "/Users/private" not in body["artifact"]["content"]
    assert "tasks.db" not in body["artifact"]["content"]
    assert "Traceback" not in body["artifact"]["content"]
    assert "checkpoint" not in body["artifact"]["content"].lower()
    assert body["artifact"]["content_hash"] == hashlib.sha256(
        body["artifact"]["content"].encode("utf-8")
    ).hexdigest()


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


def test_result_ready_talent_accepts_decision_brief_hash_contract(
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
            {
                "artifact_id": "decision-brief.md",
                "kind": "decision_brief_markdown",
                "media_type": "text/markdown",
                "content": "# Decision Brief",
                "content_hash": "a" * 64,
            }
        ],
    )

    response = client.get(
        f"/api/runs/{created['run_id']}/result",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["artifact"]["content_hash"] == "a" * 64
