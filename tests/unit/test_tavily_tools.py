"""Tavily tool retry, timeout, and structured result tests."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_internet_search_returns_results(monkeypatch):
    from tools import tavily_tools

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    provider_payload = {
        "answer": "bounded answer",
        "results": [
            {
                "title": "Test",
                "url": "https://example.com/source",
                "content": "accepted",
                "score": 0.9,
            },
            {
                "title": "Rejected",
                "url": "http://example.com/source",
                "content": "must not escape",
            },
        ],
    }
    monkeypatch.setattr(
        tavily_tools,
        "_tavily_search",
        AsyncMock(return_value=provider_payload),
    )
    report_end = MagicMock()
    monkeypatch.setattr(tavily_tools.monitor, "report_end", report_end)
    monkeypatch.setattr(tavily_tools.monitor, "report_tool", MagicMock())

    result = tavily_tools.internet_search.invoke(
        {"query": "source admission mixed boundary"}
    )

    expected = {
        "answer": "bounded answer",
        "results": [provider_payload["results"][0]],
    }
    assert result == expected
    assert result["results"][0] is not provider_payload["results"][0]
    report_end.assert_called_once_with("网络搜索工具", expected)
    assert "Rejected" not in repr(report_end.call_args)


def test_search_timeout_and_domain_scope_passed_to_sdk(monkeypatch):
    from tools.tavily_tools import _tavily_search

    client = MagicMock()
    client.search.return_value = {"results": []}
    monkeypatch.setattr("tavily.TavilyClient", lambda api_key: client)

    import asyncio

    result = asyncio.run(
        _tavily_search(
            query="test",
            max_results=5,
            topic="general",
            include_raw_content=False,
            timeout=15,
            include_domains=("jobs.example.com",),
        )
    )

    assert result == {"results": []}
    assert client.search.call_args.kwargs == {
        "max_results": 5,
        "include_raw_content": False,
        "topic": "general",
        "timeout": 15,
        "include_domains": ("jobs.example.com",),
    }


def test_internet_search_without_api_key_returns_error(monkeypatch):
    from tools.tavily_tools import clear_search_cache, internet_search

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    clear_search_cache()

    assert "Error" in internet_search.invoke({"query": "test"})


@pytest.mark.asyncio
async def test_search_with_resilience_retries_transient_failures(monkeypatch):
    from tools import tavily_tools

    calls = 0

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("transient")
        return {
            "results": [
                {
                    "title": "Found",
                    "url": "https://example.com/found",
                }
            ]
        }

    monkeypatch.setattr(tavily_tools, "_tavily_search", flaky)

    result = await tavily_tools._cached_search_with_resilience(
        "test query",
        5,
        "general",
        False,
    )

    assert calls == 3
    assert result == {
        "results": [
            {
                "title": "Found",
                "url": "https://example.com/found",
            }
        ]
    }


@pytest.mark.asyncio
async def test_search_boundary_returns_empty_results_when_all_provider_rows_invalid(
    monkeypatch,
):
    from tools import tavily_tools

    provider_payload = {
        "answer": "bounded answer",
        "results": [
            {"url": "http://example.com/source", "content": "http"},
            {"url": "https://localhost/source", "content": "local"},
        ],
    }
    search = AsyncMock(return_value=provider_payload)
    monkeypatch.setattr(tavily_tools, "_tavily_search", search)

    result = await tavily_tools._cached_search_with_resilience(
        "source admission all invalid",
        5,
        "general",
        False,
    )

    assert result == {"answer": "bounded answer", "results": []}
    search.assert_awaited_once()
