"""Tests for research run evidence and quality contracts."""
import json

import pytest


class TestResearchEvidence:
    def test_stream_evidence_merges_by_content_fingerprint(self):
        from agent.research import (
            EvidenceEntry,
            merge_evidence_entries,
        )

        stream_entry = EvidenceEntry(
            thread_id="thread-001",
            query_text="query",
            subagent_name="network_search",
            tool_name="tavily_search",
            source_url="https://example.com/source",
            snippet="Same   content",
        )
        stream_entries = [
            EvidenceEntry(
                thread_id="thread-001",
                query_text="query",
                subagent_name="network_search",
                tool_name="internet_search",
                source_url="https://example.com/source",
                snippet="Same content",
            ),
            EvidenceEntry(
                thread_id="thread-001",
                query_text="query",
                subagent_name="network_search",
                tool_name="internet_search",
                source_url="https://example.com/source",
                snippet="Changed content",
            ),
        ]

        merged = merge_evidence_entries([stream_entry], stream_entries)

        assert len(merged) == 2
        assert {entry.snippet for entry in merged} == {"Same   content", "Changed content"}
        assert all(entry.evidence_fingerprint for entry in merged)

    def test_mark_cited_evidence_matches_report_urls(self):
        from agent.research import EvidenceEntry, mark_cited_evidence

        entries = [
            EvidenceEntry(
                thread_id="thread-001",
                query_text="query",
                subagent_name="network_search",
                tool_name="tavily_search",
                source_url="https://example.com/source",
                snippet="source summary",
            )
        ]

        marked = mark_cited_evidence(
            entries,
            "Final report cites https://example.com/source for the claim.",
        )

        assert marked[0].citation_status == "cited"

    def test_mark_cited_evidence_does_not_match_url_prefix_only(self):
        from agent.research import EvidenceEntry, mark_cited_evidence

        entries = [
            EvidenceEntry(
                thread_id="thread-001",
                query_text="query",
                subagent_name="network_search",
                tool_name="tavily_search",
                source_url="https://example.com/source",
                snippet="source summary",
            )
        ]

        marked = mark_cited_evidence(
            entries,
            "Final report cites https://example.com/source-extra instead.",
        )

        assert marked[0].citation_status == "uncited"

    def test_extract_evidence_skips_untrusted_plain_text_without_url(self):
        from agent.research import extract_evidence_entries

        entries = extract_evidence_entries(
            thread_id="thread-001",
            query_text="query",
            subagent_name="shell",
            tool_name="execute",
            content="command failed with exit code 1",
        )

        assert entries == []

    def test_extract_evidence_skips_mapping_without_url_or_source_fields(self):
        from agent.research import extract_evidence_entries

        entries = extract_evidence_entries(
            thread_id="thread-001",
            query_text="query",
            subagent_name="database",
            tool_name="sql_query",
            content={"row_count": 3, "status": "ok"},
        )

        assert entries == []

    def test_quality_gate_fails_fallback_report(self, tmp_path):
        from agent.research import evaluate_report_quality

        fallback_report = tmp_path / "fallback_report.md"
        fallback_report.write_text("fallback", encoding="utf-8")

        quality = evaluate_report_quality(
            report_path=fallback_report,
            fallback_used=True,
            evidence_entries=[],
            token_usage={"total_tokens": 10},
            diagnostics=["tool:tavily_search"],
        )

        assert quality.status == "failed"
        assert any(issue["code"] == "fallback_report" for issue in quality.issues)


class TestResearchPersistence:
    def test_save_and_get_research_run_with_evidence(self, tmp_path):
        from api.persistence import (
            get_research_run_with_evidence,
            init_db,
            save_research_run,
            replace_evidence_entries,
        )
        from agent.research import EvidenceEntry

        db_path = str(tmp_path / "tasks.db")
        init_db(db_path)
        save_research_run(
            db_path=db_path,
            thread_id="thread-001",
            query="query",
            status="completed",
            started_at="2026-06-08T00:00:00+00:00",
            completed_at="2026-06-08T00:01:00+00:00",
            output_path="/tmp/report.md",
            fallback_used=False,
            assistant_calls=2,
            tool_starts=3,
            diagnostics_json=json.dumps(["tool:tavily_search"]),
            token_usage_json=json.dumps({"total_tokens": 123}),
            quality_report_json=json.dumps({"status": "passed", "issues": []}),
        )
        replace_evidence_entries(
            db_path,
            "thread-001",
            [
                EvidenceEntry(
                    thread_id="thread-001",
                    query_text="query",
                    subagent_name="network_search",
                    tool_name="tavily_search",
                    source_url="https://example.com/source",
                    snippet="source summary",
                    citation_status="cited",
                    verification_status="unverified",
                )
            ],
        )

        result = get_research_run_with_evidence(db_path, "thread-001")

        assert result["thread_id"] == "thread-001"
        assert result["quality_report"]["status"] == "passed"
        assert result["token_usage"]["total_tokens"] == 123
        assert result["evidence"][0]["source_url"] == "https://example.com/source"
        assert result["evidence"][0]["citation_status"] == "cited"

    def test_research_run_upsert_preserves_created_at(self, tmp_path):
        from api.persistence import get_research_run_with_evidence, init_db, save_research_run

        db_path = str(tmp_path / "tasks.db")
        init_db(db_path)
        save_research_run(
            db_path=db_path,
            thread_id="thread-001",
            query="first query",
            status="running",
        )
        first = get_research_run_with_evidence(db_path, "thread-001")

        save_research_run(
            db_path=db_path,
            thread_id="thread-001",
            query="updated query",
            status="completed",
        )
        second = get_research_run_with_evidence(db_path, "thread-001")

        assert second["query"] == "updated query"
        assert second["created_at"] == first["created_at"]

    def test_save_task_upsert_preserves_created_at(self, tmp_path):
        from api.persistence import get_task, init_db, save_task

        db_path = str(tmp_path / "tasks.db")
        init_db(db_path)
        save_task(db_path=db_path, thread_id="thread-001", query="first", status="pending")
        first = get_task(db_path=db_path, thread_id="thread-001")

        save_task(db_path=db_path, thread_id="thread-001", query="updated", status="running")
        second = get_task(db_path=db_path, thread_id="thread-001")

        assert second["query"] == "updated"
        assert second["created_at"] == first["created_at"]

    def test_replace_evidence_entries_rolls_back_delete_when_insert_fails(self, tmp_path):
        from api.persistence import (
            get_research_run_with_evidence,
            init_db,
            replace_evidence_entries,
            save_research_run,
        )
        from agent.research import EvidenceEntry

        db_path = str(tmp_path / "tasks.db")
        init_db(db_path)
        save_research_run(
            db_path=db_path,
            thread_id="thread-001",
            query="query",
            status="completed",
        )
        replace_evidence_entries(
            db_path=db_path,
            thread_id="thread-001",
            entries=[
                EvidenceEntry(
                    thread_id="thread-001",
                    query_text="query",
                    subagent_name="network_search",
                    tool_name="tavily_search",
                    source_url="https://example.com/source",
                    snippet="source summary",
                )
            ],
        )

        broken = EvidenceEntry(
            thread_id="thread-001",
            query_text="query",
            subagent_name="network_search",
            tool_name="tavily_search",
            source_url="https://example.com/new",
            snippet="new summary",
        )
        object.__setattr__(broken, "snippet", None)

        with pytest.raises(Exception):
            replace_evidence_entries(
                db_path=db_path,
                thread_id="thread-001",
                entries=[broken],
            )

        result = get_research_run_with_evidence(db_path, "thread-001")
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["source_url"] == "https://example.com/source"
