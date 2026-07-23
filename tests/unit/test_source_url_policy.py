"""Publishable source URL admission tests."""
from __future__ import annotations

from copy import deepcopy

import pytest


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/source",
        "https://docs.example.com/a/b",
        "https://example.com:443/source",
    ],
)
def test_publishable_source_url_accepts_canonical_public_https(value: str) -> None:
    from agent.source_url_policy import is_publishable_source_url

    assert is_publishable_source_url(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com/source",
        "https:///missing-host",
        "https://user@example.com/source",
        "https://user:password@example.com/source",
        "https://localhost/source",
        "https://api.localhost/source",
        "https://example.local/source",
        "https://example.internal/source",
        "https://example.com./source",
        "https://EXAMPLE.com/source",
        "https://example.com/source?query=1",
        "https://example.com/source#fragment",
        "https://example.com:8443/source",
        "https://example.com/source.",
        "https://127.0.0.1/source",
        "https://10.0.0.1/source",
        "https://169.254.1.1/source",
        "https://8.8.8.8/source",
        "https://[::1]/source",
        "https://example.com/ünicode",
        "https://éxample.com/source",
        "https://example.com/source\nnext",
        "https://example.com/" + ("a" * 2049),
        "",
        None,
        7,
        {"url": "https://example.com/source"},
    ],
)
def test_publishable_source_url_rejects_noncanonical_or_unsafe_values(
    value: object,
) -> None:
    from agent.source_url_policy import is_publishable_source_url

    assert is_publishable_source_url(value) is False


def test_publishable_source_url_rejects_unencodable_text() -> None:
    from agent.source_url_policy import is_publishable_source_url

    assert is_publishable_source_url("https://example.com/\ud800") is False


def test_filter_publishable_search_response_copies_and_preserves_admitted_rows() -> None:
    from agent.source_url_policy import filter_publishable_search_response

    payload = {
        "answer": "Rejected source: http://localhost/private",
        "images": ["http://localhost/private.png"],
        "provider_debug": {"raw_url": "http://127.0.0.1/private"},
        "future_field": {"raw_results": ["http://example.com/rejected"]},
        "results": [
            {
                "title": "First",
                "url": "https://example.com/first",
                "content": "first content",
                "score": 0.9,
            },
            {
                "title": "Rejected",
                "url": "http://example.com/rejected",
                "content": "must not escape",
            },
            {
                "title": "Second",
                "url": "https://docs.example.com/second",
                "content": "second content",
                "score": 0.8,
            },
        ],
    }
    original = deepcopy(payload)

    filtered = filter_publishable_search_response(payload)

    assert filtered == {
        "results": [
            payload["results"][0],
            payload["results"][2],
        ],
    }
    assert filtered is not payload
    assert filtered["results"] is not payload["results"]
    assert filtered["results"][0] is not payload["results"][0]
    assert payload == original
    assert "rejected" not in repr(filtered)


def test_filter_publishable_search_response_returns_empty_results_when_all_invalid() -> None:
    from agent.source_url_policy import filter_publishable_search_response

    assert filter_publishable_search_response(
        {
            "answer": "Rejected source: http://localhost/private",
            "images": ["http://localhost/private.png"],
            "provider_debug": {"raw_url": "http://127.0.0.1/private"},
            "future_field": {"raw_results": ["http://example.com/source"]},
            "results": [
                {"url": "http://example.com/source"},
                {"url": "https://localhost/source"},
                {"title": "missing URL"},
            ],
        }
    ) == {"results": []}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"results": None},
        {"results": ()},
        {"results": [{"url": "https://example.com/source"}] * 101},
    ],
)
def test_filter_publishable_search_response_fails_closed_for_malformed_payload(
    payload: object,
) -> None:
    from agent.source_url_policy import filter_publishable_search_response

    assert filter_publishable_search_response(payload) == {"results": []}
