"""Integration tests for research run API endpoints."""
import json
import os

from fastapi.testclient import TestClient

from api.server import app


AUTH_HEADERS = {"X-API-Key": "test-integration-key"}


def test_get_research_run_returns_run_and_evidence(tmp_path, monkeypatch):
    from api.persistence import init_db, save_research_run, replace_evidence_entries
    from agent.research import EvidenceEntry

    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(db_path))
    os.environ["API_SECRET"] = "test-integration-key"
    init_db(str(db_path))
    save_research_run(
        thread_id="thread-api",
        query="query",
        status="completed",
        started_at="2026-06-08T00:00:00+00:00",
        completed_at="2026-06-08T00:01:00+00:00",
        output_path="/tmp/report.md",
        fallback_used=False,
        assistant_calls=1,
        tool_starts=1,
        diagnostics_json=json.dumps(["tool:tavily_search"]),
        token_usage_json=json.dumps({"total_tokens": 321}),
        quality_report_json=json.dumps({"status": "passed", "issues": []}),
    )
    replace_evidence_entries(
        thread_id="thread-api",
        entries=[
            EvidenceEntry(
                thread_id="thread-api",
                query_text="query",
                subagent_name="network_search",
                tool_name="tavily_search",
                source_url="https://example.com/source",
                snippet="source summary",
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/research/runs/thread-api", headers=AUTH_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread-api"
    assert data["token_usage"]["total_tokens"] == 321
    assert data["evidence"][0]["source_url"] == "https://example.com/source"


def test_list_research_runs_returns_recent_runs(tmp_path, monkeypatch):
    from api.persistence import init_db, save_research_run

    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(db_path))
    os.environ["API_SECRET"] = "test-integration-key"
    init_db(str(db_path))
    save_research_run(
        thread_id="thread-list",
        query="query",
        status="completed",
        started_at="2026-06-08T00:00:00+00:00",
        completed_at="2026-06-08T00:01:00+00:00",
        output_path="/tmp/report.md",
        fallback_used=False,
        assistant_calls=1,
        tool_starts=1,
        diagnostics_json="[]",
        token_usage_json="{}",
        quality_report_json='{"status": "passed", "issues": []}',
    )

    client = TestClient(app)
    response = client.get("/api/research/runs", headers=AUTH_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["runs"][0]["thread_id"] == "thread-list"
