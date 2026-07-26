import json
from pathlib import PurePosixPath

import pytest

from agent.harness_contracts import ReportCandidate
from agent.research import EvidenceEntry
from agent.run_result import ExecutionOutcome
from api.run_result_service import build_generic_result_artifact


def _outcome(
    *,
    report="# Report\n\nSupported finding.",
    evidence=None,
):
    return ExecutionOutcome(
        thread_id="thread-1",
        query="Research question",
        session_dir=PurePosixPath("/workspace"),
        profile_id="generic-strict-citation",
        run_id="run-1",
        segment_id="segment-1",
        report_candidate=ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content=report,
        ),
        evidence_entries=list(evidence or []),
    )


def _evidence(url="https://example.com/source", *, snippet="Source context"):
    return EvidenceEntry(
        thread_id="thread-1",
        query_text="Research question",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url=url,
        snippet=snippet,
    )


def test_target_scanner_is_deterministic_and_conservative():
    from api.strict_citation_finalization import _extract_targets

    report = (
        "# Heading\n\n"
        "Plain paragraph.\n\n"
        "- List prose\n"
        "> Quote prose\n\n"
        "```python\nnot eligible\n```\n\n"
        "| table | row |\n\n"
        "Secret password=value\n\n"
        "Final paragraph."
    )

    targets = _extract_targets(report)

    assert [target.target_id for target in targets] == [
        "t001",
        "t002",
        "t003",
        "t004",
    ]
    assert [target.excerpt for target in targets] == [
        "Plain paragraph.",
        "- List prose",
        "> Quote prose",
        "Final paragraph.",
    ]
    for target in targets:
        assert report[target.start : target.end] == target.excerpt
        assert len(target.basis_sha256) == 64


def test_target_scanner_excludes_ambiguous_blocks_and_bounds_utf8():
    from api.strict_citation_finalization import _extract_targets

    report = (
        "Setext heading\n---\n\n"
        "[ref]: https://example.com\n    continuation\n\n"
        "<div>\nhtml\n</div>\n\n"
        "> ```\n> fenced\n> ```\n\n"
        "pipe \\| remains ambiguous\n\n"
        + ("界" * 300)
    )

    targets = _extract_targets(report)

    assert len(targets) == 1
    assert len(targets[0].excerpt.encode("utf-8")) <= 512


def test_source_projection_deduplicates_and_omits_sensitive_context():
    from api.strict_citation_finalization import _project_sources

    outcome = _outcome(
        evidence=[
            _evidence("https://example.com/a(b", snippet="password=hidden"),
            _evidence("https://example.com/a(b", snippet="duplicate"),
            _evidence("http://example.com/not-public"),
            _evidence("https://example.com/unsafe>"),
        ]
    )

    sources = _project_sources(outcome)

    assert [(source.source_id, source.source_url) for source in sources] == [
        ("s001", "https://example.com/a(b")
    ]
    assert sources[0].snippet == "[context omitted]"


def test_prepare_builds_bounded_canonical_untrusted_packet():
    from api.strict_citation_finalization import (
        PreparedStrictCitation,
        prepare_strict_citation,
    )

    outcome = _outcome(evidence=[_evidence()])
    prepared = prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )

    assert isinstance(prepared, PreparedStrictCitation)
    assert [type(message).__name__ for message in prepared.messages] == [
        "SystemMessage",
        "HumanMessage",
    ]
    packet_text = prepared.messages[1].content
    assert packet_text.startswith("BEGIN_UNTRUSTED_PACKET\n")
    assert packet_text.endswith("\nEND_UNTRUSTED_PACKET")
    payload = json.loads(packet_text.splitlines()[1])
    assert set(payload) == {"instruction", "schema", "sources", "targets"}
    assert payload["sources"][0]["source_id"] == "s001"
    assert len(packet_text.encode("utf-8")) <= 512 * 1024


@pytest.mark.parametrize(
    ("report", "evidence", "code"),
    [
        ("# Heading", [_evidence()], "strict_citation_target_unavailable"),
        ("Supported finding.", [], "strict_citation_source_unavailable"),
    ],
)
def test_prepare_fails_closed_before_invocation(report, evidence, code):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        prepare_strict_citation,
    )

    outcome = _outcome(report=report, evidence=evidence)
    with pytest.raises(StrictCitationFinalizationError, match=code):
        prepare_strict_citation(
            outcome=outcome,
            initial_artifact=build_generic_result_artifact(outcome),
        )
