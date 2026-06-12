def test_talent_public_search_fails_closed_without_declared_public_sources():
    from tools.talent_search import talent_public_search

    result = talent_public_search.invoke({"query": "AI agent engineer"})

    assert result["status"] == "error"
    assert result["error"]["code"] == "missing_declared_public_sources"


def test_talent_public_search_scopes_query_and_filters_results(monkeypatch):
    from api.context import (
        _allowed_source_domains_ctx,
        _run_id_ctx,
        set_allowed_source_domains_context,
        set_run_context,
    )
    from tools import talent_search

    captured = {}
    published = {}

    def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return {
            "results": [
                {"url": "https://jobs.example.com/role", "content": "allowed"},
                {"url": "https://other.example.net/role", "content": "rejected"},
            ]
        }

    def fake_publish(results, *, thread_id):
        published["results"] = results
        published["thread_id"] = thread_id

    monkeypatch.setattr(talent_search, "_internet_search_impl", fake_search)
    monkeypatch.setattr(talent_search, "_publish_search_evidence", fake_publish)
    domains_token = set_allowed_source_domains_context(("jobs.example.com",))
    run_token = set_run_context("run-talent")
    try:
        result = talent_search.talent_public_search.invoke(
            {"query": "AI agent engineer"}
        )
    finally:
        _run_id_ctx.reset(run_token)
        _allowed_source_domains_ctx.reset(domains_token)

    assert "site:jobs.example.com" in captured["query"]
    assert result == {
        "status": "ok",
        "results": [
            {"url": "https://jobs.example.com/role", "content": "allowed"}
        ],
    }
    assert published == {
        "results": {
            "results": [
                {"url": "https://jobs.example.com/role", "content": "allowed"}
            ]
        },
        "thread_id": "run-talent",
    }
