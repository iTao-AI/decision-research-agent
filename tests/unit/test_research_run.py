"""Tests for research run evidence and quality contracts."""


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
