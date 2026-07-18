"""Strict contracts for the frozen runtime access policy."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from pydantic import ValidationError
from starlette.requests import Request
from starlette.websockets import WebSocket

from api.runtime_access import (
    AccessDecision,
    RequestAccessContext,
    RuntimeAccessConfigurationError,
    RuntimeAccessPolicy,
    build_http_access_context,
    build_websocket_access_context,
    credentials_match,
    decide_runtime_access,
    load_runtime_access_policy,
)


def test_source_launcher_uses_constructed_loopback_app_without_reload():
    from api import server

    with patch.object(server.uvicorn, "run") as run:
        server.run_source_server()

    run.assert_called_once_with(
        server.app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="warning",
    )


def _context(**overrides: object) -> RequestAccessContext:
    values: dict[str, object] = {
        "transport": "http",
        "direct_peer": "127.0.0.1",
        "authority_host": "127.0.0.1:8000",
        "origin": None,
        "forwarded_headers_present": False,
        "header_credential": None,
        "query_credential_present": False,
    }
    values.update(overrides)
    return RequestAccessContext(**values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), ("real-secret", "real-secret"), ("密钥", "密钥")],
)
def test_normalizes_supported_secret_values(raw: str | None, expected: str | None):
    policy = load_runtime_access_policy({} if raw is None else {"API_SECRET": raw})
    assert policy.secret_value == expected


@pytest.mark.parametrize("raw", ["your-secret-key", " ", "\t\n"])
def test_rejects_legacy_or_whitespace_only_secret(raw: str):
    with pytest.raises(
        RuntimeAccessConfigurationError,
        match="runtime_access_configuration_invalid",
    ):
        load_runtime_access_policy({"API_SECRET": raw})


def test_utf8_credentials_compare_without_type_error():
    assert credentials_match("密钥", "密钥") is True
    assert credentials_match("错误", "密钥") is False
    assert credentials_match(None, "密钥") is False


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_empty_secret_allows_explicit_loopback(peer: str):
    authority = "[::1]:8000" if peer == "::1" else "127.0.0.1:8000"
    assert decide_runtime_access(
        load_runtime_access_policy({}),
        _context(direct_peer=peer, authority_host=authority),
        allowed_origin=None,
    ) == AccessDecision(allowed=True, code="allowed_loopback")


@pytest.mark.parametrize("peer", [None, "", "testclient", "192.0.2.10", "not-an-ip"])
def test_empty_secret_rejects_unknown_or_non_loopback_peer(peer: str | None):
    assert decide_runtime_access(
        load_runtime_access_policy({}),
        _context(direct_peer=peer),
        allowed_origin=None,
    ).code == "api_auth_not_configured"


@pytest.mark.parametrize(
    "authority",
    [
        None,
        "",
        "localhost:8000",
        "192.0.2.1:8000",
        "127.0.0.1:bad",
        "127.0.0.1:",
        "[::1]:",
        "127.0.0.1/path",
        "user@127.0.0.1",
        "127.0.0.1\t",
        "127.0.0.1\n",
        "127.0.0.1\x00",
    ],
)
def test_empty_secret_rejects_unsafe_authority(authority: str | None):
    assert decide_runtime_access(
        load_runtime_access_policy({}),
        _context(authority_host=authority),
        allowed_origin=None,
    ).code == "local_authority_required"


@pytest.mark.parametrize("authority", ["127.0.0.1", "[::1]"])
def test_empty_secret_accepts_loopback_authority_without_optional_port(authority: str):
    assert decide_runtime_access(
        load_runtime_access_policy({}),
        _context(authority_host=authority),
        allowed_origin=None,
    ) == AccessDecision(allowed=True, code="allowed_loopback")


def test_forwarding_metadata_is_rejected_before_peer_classification():
    decision = decide_runtime_access(
        load_runtime_access_policy({}),
        _context(direct_peer="192.0.2.10", forwarded_headers_present=True),
        allowed_origin=None,
    )
    assert decision == AccessDecision(allowed=False, code="forwarded_request_rejected")


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [(None, "api_key_invalid"), ("wrong", "api_key_invalid"), ("密钥", "allowed_api_key")],
)
def test_configured_secret_requires_matching_header_for_every_peer(
    supplied: str | None,
    expected: str,
):
    decision = decide_runtime_access(
        load_runtime_access_policy({"API_SECRET": "密钥"}),
        _context(direct_peer="192.0.2.10", authority_host="example.com", header_credential=supplied),
        allowed_origin=None,
    )
    assert decision.code == expected
    assert decision.allowed is (expected == "allowed_api_key")


def test_websocket_query_credential_is_rejected_first():
    decision = decide_runtime_access(
        load_runtime_access_policy({"API_SECRET": "correct"}),
        _context(
            transport="websocket",
            origin="https://wrong.example",
            header_credential="correct",
            query_credential_present=True,
        ),
        allowed_origin="https://allowed.example",
    )
    assert decision.code == "query_credential_rejected"


def test_present_origin_must_match_exact_configured_origin():
    decision = decide_runtime_access(
        load_runtime_access_policy({"API_SECRET": "correct"}),
        _context(origin="https://wrong.example", header_credential="correct"),
        allowed_origin="https://allowed.example",
    )
    assert decision.code == "origin_not_allowed"


def test_policy_can_disable_unauthenticated_loopback():
    policy = RuntimeAccessPolicy(api_secret=None, allow_unauthenticated_loopback=False)
    assert decide_runtime_access(policy, _context(), allowed_origin=None).code == (
        "api_auth_not_configured"
    )


def test_contract_models_are_frozen_strict_and_forbid_extra_fields():
    policy = load_runtime_access_policy({})
    with pytest.raises(ValidationError):
        policy.allow_unauthenticated_loopback = False
    with pytest.raises(ValidationError):
        RuntimeAccessPolicy(api_secret=None, allow_unauthenticated_loopback=1)
    with pytest.raises(ValidationError):
        RequestAccessContext(**_context().model_dump(), unexpected=True)
    with pytest.raises(ValidationError):
        AccessDecision(allowed=1, code="allowed_loopback")


def _request(*, headers: list[tuple[bytes, bytes]], client=("127.0.0.1", 50000)) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/runs",
            "raw_path": b"/api/runs",
            "query_string": b"",
            "headers": headers,
            "client": client,
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
            "http_version": "1.1",
        }
    )


def _websocket(*, headers: list[tuple[bytes, bytes]], query: bytes = b"") -> WebSocket:
    async def receive():
        return {"type": "websocket.disconnect"}

    async def send(_message):
        return None

    return WebSocket(
        {
            "type": "websocket",
            "path": "/ws/runs/run_1",
            "raw_path": b"/ws/runs/run_1",
            "query_string": query,
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8000),
            "scheme": "ws",
            "subprotocols": [],
        },
        receive=receive,
        send=send,
    )


def test_http_context_builder_extracts_only_bounded_selected_fields():
    context = build_http_access_context(
        _request(
            headers=[
                (b"host", b"127.0.0.1:8000"),
                (b"x-api-key", "密钥".encode()),
                (b"origin", b"http://127.0.0.1:5173"),
                (b"x-forwarded-for", b""),
                (b"x-unrelated", b"ignored"),
            ]
        )
    )
    assert context == _context(
        authority_host="127.0.0.1:8000",
        origin="http://127.0.0.1:5173",
        forwarded_headers_present=True,
        header_credential="密钥",
    )


def test_duplicate_selected_headers_fail_closed():
    context = build_http_access_context(
        _request(
            headers=[
                (b"host", b"127.0.0.1"),
                (b"host", b"127.0.0.1:8000"),
                (b"x-api-key", b"one"),
                (b"x-api-key", b"two"),
                (b"origin", b"https://one.example"),
                (b"origin", b"https://two.example"),
            ]
        )
    )
    assert context.authority_host is None
    assert context.header_credential is None
    assert context.origin == "__invalid_duplicate_origin__"


def test_websocket_context_detects_query_key_presence_without_copying_value():
    context = build_websocket_access_context(
        _websocket(
            headers=[(b"host", b"127.0.0.1:8000")],
            query=b"other=1&api_key=do-not-copy",
        )
    )
    assert context.transport == "websocket"
    assert context.query_credential_present is True
    assert "do-not-copy" not in repr(context)


@pytest.mark.parametrize(
    "query",
    [
        b"api_key=would-be-logged&invalid=\xff",
        b"%61pi_key=would-be-logged",
        b"api%5Fkey=would-be-logged",
    ],
)
def test_websocket_context_detects_query_key_without_decoding_values(query: bytes):
    context = build_websocket_access_context(
        _websocket(
            headers=[(b"host", b"127.0.0.1:8000")],
            query=query,
        )
    )

    assert context.query_credential_present is True
    assert "would-be-logged" not in repr(context)
