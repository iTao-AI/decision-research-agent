from datetime import datetime, timezone


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


def test_content_hash_excludes_generated_at_but_includes_versions():
    from api.decision_brief import with_content_hash

    first = with_content_hash(_brief())
    changed_time = _brief().model_copy(
        update={"generated_at": datetime(2026, 6, 13, tzinfo=timezone.utc)}
    )
    changed_renderer = _brief().model_copy(update={"renderer_version": "2"})

    assert with_content_hash(changed_time).content_hash == first.content_hash
    assert with_content_hash(changed_renderer).content_hash != first.content_hash


def test_markdown_renderer_is_byte_stable():
    from api.decision_brief import render_markdown, with_content_hash

    brief = with_content_hash(_brief())

    assert render_markdown(brief).encode("utf-8") == render_markdown(brief).encode("utf-8")
    assert "# Talent Hiring Signal Decision Brief" in render_markdown(brief)
    assert brief.content_hash in render_markdown(brief)
