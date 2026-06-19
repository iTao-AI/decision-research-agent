from datetime import datetime, timezone
from pathlib import Path

import pytest


FIXTURE_DIR = Path("tests/fixtures")
FIXTURE_JSON = FIXTURE_DIR / "talent-decision-brief-renderer-v2.json"
FIXTURE_MARKDOWN = FIXTURE_DIR / "talent-decision-brief-renderer-v2.md"


def _brief():
    from agent.talent_contracts import DecisionBrief, ResearchScope

    scope = ResearchScope.model_validate(
        {
            "target_roles": ["AI Agent Engineer"],
            "target_companies": ["Example Company"],
            "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
            "declared_samples": [],
            "allowed_source_types": ["public_job_posting"],
            "research_questions": ["Which skills recur?"],
            "requested_outputs": ["decision_brief"],
        }
    )
    return DecisionBrief(
        schema_version="1",
        run_id="run-1",
        profile_id="talent-hiring-signal",
        profile_version="1",
        input_snapshot_hash="input-hash",
        renderer_version="1",
        canonicalization_version="1",
        scope=scope,
        executive_summary="Summary",
        findings=[],
        claims=[],
        evidence_summary=[],
        conflicts=[],
        limitations=["Declared sample only."],
        recommendations=["Validate against target roles."],
        review_summary={"status": "not_required"},
        quality_summary={"status": "passed"},
        generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )


def _fixture_brief():
    from agent.talent_contracts import DecisionBrief

    return DecisionBrief.model_validate_json(FIXTURE_JSON.read_text(encoding="utf-8"))


def _render(brief=None):
    from api.decision_brief import render_markdown, with_content_hash

    return render_markdown(with_content_hash(brief or _fixture_brief()))


def _section(markdown: str, start: str, end: str) -> str:
    return markdown.split(start, 1)[1].split(end, 1)[0]


def test_content_hash_excludes_generated_at_but_includes_versions():
    from api.decision_brief import render_markdown, with_content_hash

    first = with_content_hash(_brief())
    changed_time = _brief().model_copy(
        update={"generated_at": datetime(2026, 6, 13, tzinfo=timezone.utc)}
    )
    changed_renderer = _brief().model_copy(update={"renderer_version": "2"})

    assert with_content_hash(changed_time).content_hash == first.content_hash
    assert with_content_hash(changed_renderer).content_hash != first.content_hash
    assert render_markdown(with_content_hash(changed_time)) != render_markdown(first)


def test_renderer_v2_matches_byte_exact_golden_fixture():
    expected = FIXTURE_MARKDOWN.read_bytes()

    assert _render().encode("utf-8") == expected


def test_snapshot_preserves_canonical_order_caps_at_three_and_excludes_claims():
    markdown = _render()
    snapshot = _section(markdown, "## Decision Snapshot", "## Scope And Coverage")

    assert "Declared source references: 1" in snapshot
    assert snapshot.index("finding-a") < snapshot.index("finding-b")
    assert snapshot.index("finding-b") < snapshot.index("finding-c")
    assert "finding-d" not in snapshot
    assert "finding-missing" not in snapshot
    assert "finding-unverified" not in snapshot
    assert "claim-pending" not in snapshot
    assert "claim-conflicting" not in snapshot
    assert "4 verified evidence-backed findings; 3 shown" in snapshot


def test_complete_findings_and_candidate_claims_remain_in_appendices():
    markdown = _render()
    findings = _section(
        markdown,
        "## Detailed Findings Appendix",
        "## Candidate Claims Appendix",
    )
    claims = _section(
        markdown,
        "## Candidate Claims Appendix",
        "## Artifact Metadata",
    )

    for finding_id in (
        "finding-a",
        "finding-missing",
        "finding-b",
        "finding-unverified",
        "finding-c",
        "finding-d",
    ):
        assert f"### {finding_id}" in findings
    assert "### claim-pending" in claims
    assert "### claim-conflicting" in claims


def test_zero_evidence_and_global_conflicts_fail_closed_without_claim_fallback():
    no_evidence = _fixture_brief().model_copy(update={"evidence_summary": []})
    conflicted = _fixture_brief().model_copy(update={"conflicts": ["global conflict"]})

    for brief in (no_evidence, conflicted):
        snapshot = _section(_render(brief), "## Decision Snapshot", "## Scope And Coverage")
        assert "No verified evidence-backed findings are available for the snapshot." in snapshot
        assert "finding-a" not in snapshot
        assert "claim-pending" not in snapshot


def test_malformed_conflicts_and_contradictions_fail_closed():
    fixture = _fixture_brief()
    malformed_global = fixture.model_copy(update={"conflicts": [None]})
    malformed_finding = fixture.findings[0].model_copy(
        update={"contradictions": [None]}
    )
    malformed_local = fixture.model_copy(
        update={"findings": [malformed_finding, *fixture.findings[1:]]}
    )

    global_snapshot = _section(
        _render(malformed_global),
        "## Decision Snapshot",
        "## Scope And Coverage",
    )
    local_snapshot = _section(
        _render(malformed_local),
        "## Decision Snapshot",
        "## Scope And Coverage",
    )

    assert "finding-a" not in global_snapshot
    assert "finding-a" not in local_snapshot


def test_empty_brief_uses_explicit_finding_and_claim_states():
    brief = _fixture_brief().model_copy(
        update={"findings": [], "claims": [], "evidence_summary": []}
    )

    markdown = _render(brief)

    assert "No findings are present in this brief." in markdown
    assert "No candidate claims are present in this brief." in markdown
    assert "Evidence records | 0" in markdown


@pytest.mark.parametrize(
    "evidence_summary",
    [
        [None],
        [{"evidence_id": [], "verification_status": "verified"}],
        [{"evidence_id": "", "verification_status": "verified"}],
        [{"evidence_id": "ev-a", "verification_status": "pending"}],
        [
            {"evidence_id": "ev-a", "verification_status": "verified"},
            {"evidence_id": "ev-a", "verification_status": "verified"},
        ],
    ],
)
def test_malformed_or_ambiguous_evidence_never_makes_finding_eligible(
    evidence_summary,
):
    brief = _fixture_brief().model_copy(update={"evidence_summary": evidence_summary})

    snapshot = _section(_render(brief), "## Decision Snapshot", "## Scope And Coverage")

    assert "No verified evidence-backed findings are available for the snapshot." in snapshot
    assert "finding-a" not in snapshot


def test_unhashable_evidence_status_fails_closed_without_crashing():
    brief = _fixture_brief().model_copy(
        update={
            "evidence_summary": [
                {"evidence_id": "ev-a", "verification_status": []}
            ]
        }
    )

    snapshot = _section(_render(brief), "## Decision Snapshot", "## Scope And Coverage")

    assert "No verified evidence-backed findings are available for the snapshot." in snapshot
    assert "finding-a" not in snapshot


def test_empty_or_mixed_evidence_refs_never_fail_open():
    fixture = _fixture_brief()
    empty = fixture.findings[0].model_copy(update={"evidence_refs": []})
    mixed = fixture.findings[0].model_copy(
        update={"evidence_refs": ["ev-a", "ev-u"]}
    )

    for changed in (empty, mixed):
        brief = fixture.model_copy(update={"findings": [changed, *fixture.findings[1:]]})
        snapshot = _section(
            _render(brief),
            "## Decision Snapshot",
            "## Scope And Coverage",
        )
        assert "finding-a" not in snapshot


def test_counts_ignore_quality_summary_and_non_bool_review_flag_is_not_coerced():
    brief = _fixture_brief().model_copy(
        update={
            "quality_summary": {
                "finding_count": "999",
                "claim_count": [],
                "evidence_count": {"bad": True},
            },
            "review_summary": {
                "status": "unknown",
                "required_before_delivery": "false",
            },
        }
    )

    snapshot = _section(_render(brief), "## Decision Snapshot", "## Scope And Coverage")

    assert "| Findings | 6 |" in snapshot
    assert "| Candidate claims | 2 |" in snapshot
    assert "| Evidence records | 5 |" in snapshot
    assert "| Review bundle status | Not declared |" in snapshot
    assert "| Review required before delivery | Not declared |" in snapshot


def test_unhashable_review_status_renders_not_declared_without_crashing():
    brief = _fixture_brief().model_copy(
        update={
            "review_summary": {
                "status": [],
                "required_before_delivery": False,
            }
        }
    )

    snapshot = _section(_render(brief), "## Decision Snapshot", "## Scope And Coverage")

    assert "| Review bundle status | Not declared |" in snapshot
    assert "| Review required before delivery | No |" in snapshot


def test_untrusted_text_cannot_emit_html_images_or_markdown_structure():
    markdown = _render()

    assert "<script>" not in markdown
    assert "<b>pending</b>" not in markdown
    assert "![image]" not in markdown
    assert "&lt;script&gt;" in markdown
    assert r"\!\[image\]\(https://evil.example/x\)" in markdown
    assert r"\# forged heading" in markdown
    assert sum(line.startswith("|") for line in markdown.splitlines()) == 9


def test_html_entities_are_not_broken_by_markdown_escaping():
    fixture = _fixture_brief()
    quoted = fixture.findings[0].model_copy(
        update={"statement": "Recruiters don't treat \"confidence\" as priority."}
    )
    brief = fixture.model_copy(update={"findings": [quoted, *fixture.findings[1:]]})

    markdown = _render(brief)

    assert "Recruiters don&#x27;t treat &quot;confidence&quot; as priority." in markdown
    assert "&\\#x27;" not in markdown


def test_line_separators_controls_and_backticks_are_normalized():
    fixture = _fixture_brief()
    hostile = fixture.findings[0].model_copy(
        update={
            "statement": "first\r\nsecond\u2028third\u2029fourth\x00\u202e`code`"
        }
    )
    brief = fixture.model_copy(update={"findings": [hostile, *fixture.findings[1:]]})

    markdown = _render(brief)

    assert "first<br>second<br>third<br>fourth\\`code\\`" in markdown
    assert "\r" not in markdown
    assert "\x00" not in markdown
    assert "\u2028" not in markdown
    assert "\u2029" not in markdown
    assert "\u202e" not in markdown


def test_large_brief_keeps_complete_appendix_while_snapshot_stays_bounded():
    fixture = _fixture_brief()
    findings = [
        fixture.findings[0].model_copy(
            update={
                "finding_id": f"finding-scale-{index:03d}",
                "statement": f"Scale finding {index}",
            }
        )
        for index in range(200)
    ]
    brief = fixture.model_copy(update={"findings": findings, "claims": []})

    markdown = _render(brief)
    snapshot = _section(markdown, "## Decision Snapshot", "## Scope And Coverage")
    appendix = _section(
        markdown,
        "## Detailed Findings Appendix",
        "## Candidate Claims Appendix",
    )

    assert snapshot.count("#### finding-scale-") == 3
    assert appendix.count("### finding-scale-") == 200
    assert "### finding-scale-199" in appendix


def test_recommendations_section_is_omitted_when_contract_has_none():
    assert "## Recommendations" not in _render()
