"""CORS configuration contract tests."""

import pytest
from pydantic import ValidationError

from api.cors_config import (
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    CORS_ALLOWED_ORIGIN_ENV,
    CorsConfiguration,
    CorsConfigurationError,
    get_allowed_origins,
    load_cors_configuration,
    validate_cors_origin,
)
from api.runtime_access import load_runtime_access_policy


def test_cors_denies_browser_origins_by_default(monkeypatch) -> None:
    monkeypatch.delenv(CORS_ALLOWED_ORIGIN_ENV, raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)

    config = load_cors_configuration(access_policy=load_runtime_access_policy({}))
    assert config.allowed_origin is None
    assert config.allowed_origins == []
    assert get_allowed_origins() == []
    assert validate_cors_origin("http://localhost:5173") is False


def test_normalizes_one_exact_origin_trailing_slash() -> None:
    config = load_cors_configuration(
        access_policy=load_runtime_access_policy({"API_SECRET": "configured"}),
        environ={CORS_ALLOWED_ORIGIN_ENV: "https://example.com/"},
    )
    assert config.allowed_origin == "https://example.com"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        " ",
        "https://a.example,https://b.example",
        "ftp://example.com",
        "https://user@example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
        "https://*.example.com",
        "https://example.com:invalid",
        "http://127.0.0.1:",
        "http://[::1]:",
        "https://example.com:/",
        "http://127.0.0.1\t:5173",
        "http://127.0.0.1\n:5173",
        "http://127.0.0.1\x00:5173",
    ],
)
def test_rejects_non_origin_values(origin: str) -> None:
    with pytest.raises(CorsConfigurationError, match="cors_origin_invalid"):
        load_cors_configuration(
            access_policy=load_runtime_access_policy({"API_SECRET": "configured"}),
            environ={CORS_ALLOWED_ORIGIN_ENV: origin},
        )


def test_empty_secret_rejects_remote_browser_origin() -> None:
    with pytest.raises(
        CorsConfigurationError,
        match="cors_origin_requires_authenticated_runtime",
    ):
        load_cors_configuration(
            access_policy=load_runtime_access_policy({}),
            environ={CORS_ALLOWED_ORIGIN_ENV: "https://example.com"},
        )


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:5173", "http://[::1]:5173"],
)
def test_empty_secret_accepts_explicit_loopback_literal(origin: str) -> None:
    config = load_cors_configuration(
        access_policy=load_runtime_access_policy({}),
        environ={CORS_ALLOWED_ORIGIN_ENV: origin},
    )
    assert config.allowed_origin == origin


def test_empty_secret_rejects_localhost_dns_name() -> None:
    with pytest.raises(
        CorsConfigurationError,
        match="cors_origin_requires_authenticated_runtime",
    ):
        load_cors_configuration(
            access_policy=load_runtime_access_policy({}),
            environ={CORS_ALLOWED_ORIGIN_ENV: "http://localhost:5173"},
        )


def test_cors_surface_is_exact_and_credential_free() -> None:
    config = load_cors_configuration(
        access_policy=load_runtime_access_policy({"API_SECRET": "configured"}),
        environ={CORS_ALLOWED_ORIGIN_ENV: "https://example.com:8443"},
    )
    assert config.allowed_origins == ["https://example.com:8443"]
    assert config.allow_credentials is False
    assert config.allow_methods == ("GET", "POST", "OPTIONS")
    assert config.allow_headers == (
        "Content-Type",
        "Idempotency-Key",
        "X-API-Key",
    )
    assert CORS_ALLOWED_METHODS == config.allow_methods
    assert CORS_ALLOWED_HEADERS == config.allow_headers


def test_cors_configuration_is_frozen_strict_and_forbids_extra() -> None:
    config = CorsConfiguration(allowed_origin=None)
    with pytest.raises(ValidationError):
        config.allowed_origin = "https://example.com"
    with pytest.raises(ValidationError):
        CorsConfiguration(allowed_origin=None, allow_credentials=1)
    with pytest.raises(ValidationError):
        CorsConfiguration(allowed_origin=None, unexpected=True)


def test_compatibility_helpers_use_canonical_env_only(monkeypatch) -> None:
    monkeypatch.setenv(CORS_ALLOWED_ORIGIN_ENV, "https://example.com/")
    monkeypatch.setenv("API_SECRET", "configured")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://retired.example")

    assert get_allowed_origins() == ["https://example.com"]
    assert validate_cors_origin("https://example.com") is True
    assert validate_cors_origin("https://retired.example") is False
