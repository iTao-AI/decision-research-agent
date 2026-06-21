import json
import sqlite3

import pytest

from api.review_config import (
    ReviewConfigurationError,
    check_review_readiness,
    validate_review_runtime,
)


def test_enabled_review_requires_secret_and_explicit_persistent_paths(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.delenv("API_SECRET", raising=False)
    monkeypatch.delenv("TASKS_DB_PATH", raising=False)
    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        raising=False,
    )

    with pytest.raises(
        ReviewConfigurationError,
        match="review_auth_not_configured",
    ):
        validate_review_runtime(output_dir=tmp_path / "output")


@pytest.mark.parametrize(
    ("missing_name", "code"),
    [
        ("TASKS_DB_PATH", "review_application_db_not_configured"),
        (
            "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
            "review_checkpoint_db_not_configured",
        ),
    ],
)
def test_enabled_review_requires_each_database_path(
    tmp_path,
    monkeypatch,
    missing_name,
    code,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )
    monkeypatch.delenv(missing_name)

    with pytest.raises(ReviewConfigurationError, match=code):
        validate_review_runtime(output_dir=tmp_path / "output")


@pytest.mark.parametrize(
    ("tasks_path", "checkpoint_path", "code"),
    [
        (":memory:", "checkpoint.db", "review_application_db_not_persistent"),
        ("tasks.db", ":memory:", "review_checkpoint_db_not_persistent"),
        ("same.db", "same.db", "review_databases_must_be_separate"),
    ],
)
def test_enabled_review_rejects_unsupported_database_paths(
    tmp_path,
    monkeypatch,
    tasks_path,
    checkpoint_path,
    code,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv(
        "TASKS_DB_PATH",
        tasks_path if tasks_path == ":memory:" else str(tmp_path / tasks_path),
    )
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        (
            checkpoint_path
            if checkpoint_path == ":memory:"
            else str(tmp_path / checkpoint_path)
        ),
    )

    with pytest.raises(ReviewConfigurationError, match=code):
        validate_review_runtime(output_dir=tmp_path / "output")


def test_disabled_review_needs_no_runtime_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "false")
    monkeypatch.delenv("API_SECRET", raising=False)

    result = validate_review_runtime(output_dir=tmp_path / "output")

    assert result.enabled is False


def test_readiness_requires_exact_thirteen_gate_pass(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )
    report = tmp_path / "gate.json"
    report.write_text(
        json.dumps(
            {
                "status": "PASS",
                "expected": 13,
                "passed": 13,
                "failed": [],
            }
        ),
        encoding="utf-8",
    )
    runtime = validate_review_runtime(output_dir=tmp_path / "output")

    readiness = check_review_readiness(
        runtime=runtime,
        gate_report_path=report,
    )

    assert readiness.ready is True


def test_readiness_rejects_incomplete_existing_review_schema(
    tmp_path,
    monkeypatch,
):
    tasks_path = tmp_path / "tasks.db"
    connection = sqlite3.connect(tasks_path)
    try:
        connection.execute(
            """
            CREATE TABLE review_workflows_v2 (
                status TEXT,
                lease_expires_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL", "true")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("TASKS_DB_PATH", str(tasks_path))
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )
    report = tmp_path / "gate.json"
    report.write_text(
        json.dumps(
            {
                "status": "PASS",
                "expected": 13,
                "passed": 13,
                "failed": [],
            }
        ),
        encoding="utf-8",
    )
    runtime = validate_review_runtime(output_dir=tmp_path / "output")

    readiness = check_review_readiness(
        runtime=runtime,
        gate_report_path=report,
    )

    assert readiness.application_schema_ready is False
    assert readiness.ready is False
