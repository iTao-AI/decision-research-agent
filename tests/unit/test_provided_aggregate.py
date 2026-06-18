import json


def _write_fixture(root, aggregate_id="aggregate-v1"):
    root.mkdir(parents=True)
    (root / f"{aggregate_id}.json").write_text(
        json.dumps(
            {
                "aggregate_id": aggregate_id,
                "samples": [
                    {
                        "sample_id": "sample-1",
                        "source_url": "https://jobs.example.com/role",
                        "content": "Agent evaluation and RAG are required.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_provided_aggregate_fails_closed_when_provider_disabled(tmp_path, monkeypatch):
    from tools.provided_aggregate import provided_aggregate

    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        raising=False,
    )
    monkeypatch.delenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", raising=False)

    result = provided_aggregate.invoke({"aggregate_id": "aggregate-v1"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "provided_aggregate_disabled"


def test_canonical_fixture_flag_overrides_legacy_false(monkeypatch):
    from tools.provided_aggregate import provided_aggregate

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES",
        "true",
    )
    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "false")

    result = provided_aggregate.invoke({"aggregate_id": "aggregate-v1"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "undeclared_provided_aggregate"


def test_provided_aggregate_rejects_undeclared_aggregate(tmp_path, monkeypatch):
    from tools.provided_aggregate import provided_aggregate

    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "true")

    result = provided_aggregate.invoke({"aggregate_id": "aggregate-v1"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "undeclared_provided_aggregate"


def test_provided_aggregate_reads_only_declared_fixed_fixture_and_publishes_evidence(
    tmp_path, monkeypatch
):
    from api.context import (
        _allowed_aggregate_ids_ctx,
        _run_id_ctx,
        set_allowed_aggregate_ids_context,
        set_run_context,
    )
    from tools import provided_aggregate as aggregate_tool

    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures)
    published = {}
    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "true")
    monkeypatch.setattr(aggregate_tool, "FIXTURE_ROOT", fixtures)
    monkeypatch.setattr(
        aggregate_tool,
        "_publish_search_evidence",
        lambda results, thread_id: published.update(
            {"results": results, "thread_id": thread_id}
        ),
    )
    aggregate_token = set_allowed_aggregate_ids_context(("aggregate-v1",))
    run_token = set_run_context("run-talent")
    try:
        result = aggregate_tool.provided_aggregate.invoke(
            {"aggregate_id": "aggregate-v1"}
        )
    finally:
        _run_id_ctx.reset(run_token)
        _allowed_aggregate_ids_ctx.reset(aggregate_token)

    assert result["status"] == "ok"
    assert result["aggregate_id"] == "aggregate-v1"
    assert result["results"][0]["evidence_id"].startswith("ev_run-talent_")
    assert published["thread_id"] == "run-talent"


def test_provided_aggregate_rejects_path_like_identifier(monkeypatch):
    from api.context import _allowed_aggregate_ids_ctx, set_allowed_aggregate_ids_context
    from tools.provided_aggregate import provided_aggregate

    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "true")
    token = set_allowed_aggregate_ids_context(("../secret",))
    try:
        result = provided_aggregate.invoke({"aggregate_id": "../secret"})
    finally:
        _allowed_aggregate_ids_ctx.reset(token)

    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_provided_aggregate_id"


def test_provided_aggregate_rejects_non_utf8_fixture(tmp_path, monkeypatch):
    from api.context import _allowed_aggregate_ids_ctx, set_allowed_aggregate_ids_context
    from tools import provided_aggregate as aggregate_tool

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "aggregate-v1.json").write_bytes(b"\xff\xfe\x00")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES", "true")
    monkeypatch.setattr(aggregate_tool, "FIXTURE_ROOT", fixtures)
    token = set_allowed_aggregate_ids_context(("aggregate-v1",))
    try:
        result = aggregate_tool.provided_aggregate.invoke(
            {"aggregate_id": "aggregate-v1"}
        )
    finally:
        _allowed_aggregate_ids_ctx.reset(token)

    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_provided_aggregate_fixture"
