"""Strict singular browser Origin configuration."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from api.runtime_access import RuntimeAccessPolicy, load_runtime_access_policy


CORS_ALLOWED_ORIGIN_ENV = "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN"
CORS_ALLOWED_METHODS = ("GET", "POST", "OPTIONS")
CORS_ALLOWED_HEADERS = ("Content-Type", "Idempotency-Key", "X-API-Key")


class CorsConfigurationError(RuntimeError):
    """Bounded startup failure for an invalid browser Origin configuration."""


class CorsConfiguration(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    allowed_origin: str | None
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = CORS_ALLOWED_METHODS
    allow_headers: tuple[str, ...] = CORS_ALLOWED_HEADERS

    @property
    def allowed_origins(self) -> list[str]:
        return [] if self.allowed_origin is None else [self.allowed_origin]


def _normalize_origin(value: str) -> str:
    if not value or value != value.strip() or value in {"*", "null"} or "," in value:
        raise CorsConfigurationError("cors_origin_invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise CorsConfigurationError("cors_origin_invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or "*" in parsed.hostname
    ):
        raise CorsConfigurationError("cors_origin_invalid")
    hostname = parsed.hostname
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        rendered_host = f"{rendered_host}:{port}"
    return f"{parsed.scheme}://{rendered_host}"


def _origin_host_is_explicit_loopback(origin: str) -> bool:
    hostname = urlsplit(origin).hostname
    if hostname is None:
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address in {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}


def load_cors_configuration(
    *,
    access_policy: RuntimeAccessPolicy,
    environ: Mapping[str, str] | None = None,
) -> CorsConfiguration:
    source = os.environ if environ is None else environ
    raw_origin = source.get(CORS_ALLOWED_ORIGIN_ENV)
    if raw_origin is None or raw_origin == "":
        return CorsConfiguration(allowed_origin=None)
    allowed_origin = _normalize_origin(raw_origin)
    if access_policy.secret_value is None and not _origin_host_is_explicit_loopback(
        allowed_origin
    ):
        raise CorsConfigurationError(
            "cors_origin_requires_authenticated_runtime"
        )
    return CorsConfiguration(allowed_origin=allowed_origin)


def get_allowed_origins() -> list[str]:
    """Return the normalized canonical browser Origin allowlist."""
    return load_cors_configuration(
        access_policy=load_runtime_access_policy(),
    ).allowed_origins


def validate_cors_origin(origin: str) -> bool:
    """Return whether an Origin header is exactly the configured Origin."""
    return origin in get_allowed_origins()
