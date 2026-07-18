"""Frozen application-owned access policy for the supported local runtime."""

from __future__ import annotations

import hmac
import ipaddress
import os
from collections.abc import Mapping, Sequence
from typing import Literal
from urllib.parse import unquote_to_bytes, urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr
from starlette.requests import Request
from starlette.websockets import WebSocket


AccessDecisionCode = Literal[
    "allowed_loopback",
    "allowed_api_key",
    "api_auth_not_configured",
    "api_key_invalid",
    "local_authority_required",
    "forwarded_request_rejected",
    "origin_not_allowed",
    "query_credential_rejected",
]

FORWARDED_IDENTITY_HEADERS = frozenset(
    {
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-port",
        "x-real-ip",
        "true-client-ip",
        "cf-connecting-ip",
    }
)

_DUPLICATE_ORIGIN = "__invalid_duplicate_origin__"
_MAX_ENCODED_QUERY_KEY_BYTES = len("api_key") * 3


class RuntimeAccessConfigurationError(RuntimeError):
    """Bounded startup failure for an invalid runtime access configuration."""


class RuntimeAccessPolicy(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    api_secret: SecretStr | None
    allow_unauthenticated_loopback: bool = True

    @property
    def secret_value(self) -> str | None:
        return (
            None
            if self.api_secret is None
            else self.api_secret.get_secret_value()
        )


class RequestAccessContext(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    transport: Literal["http", "websocket"]
    direct_peer: str | None
    authority_host: str | None
    origin: str | None
    forwarded_headers_present: bool
    header_credential: str | None
    query_credential_present: bool


class AccessDecision(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    allowed: bool
    code: AccessDecisionCode


def normalize_api_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value == "your-secret-key" or value.isspace():
        raise RuntimeAccessConfigurationError(
            "runtime_access_configuration_invalid"
        )
    return value


def load_runtime_access_policy(
    environ: Mapping[str, str] | None = None,
) -> RuntimeAccessPolicy:
    source = os.environ if environ is None else environ
    value = normalize_api_secret(source.get("API_SECRET"))
    return RuntimeAccessPolicy(
        api_secret=None if value is None else SecretStr(value),
    )


def credentials_match(supplied: str | None, configured: str) -> bool:
    return hmac.compare_digest(
        (supplied or "").encode("utf-8"),
        configured.encode("utf-8"),
    )


def direct_peer_is_loopback(value: str | None) -> bool:
    if not value:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_loopback


def authority_is_explicit_loopback(value: str | None) -> bool:
    if (
        not value
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in value
        )
        or any(marker in value for marker in ("/", "?", "#", "@"))
        or value.endswith(":")
    ):
        return False
    try:
        parsed = urlsplit(f"//{value}")
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if hostname is None:
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address == ipaddress.ip_address("127.0.0.1") or address == ipaddress.ip_address("::1")


def decide_runtime_access(
    policy: RuntimeAccessPolicy,
    context: RequestAccessContext,
    *,
    allowed_origin: str | None,
) -> AccessDecision:
    if context.transport == "websocket" and context.query_credential_present:
        return AccessDecision(allowed=False, code="query_credential_rejected")
    if context.origin is not None and context.origin != allowed_origin:
        return AccessDecision(allowed=False, code="origin_not_allowed")
    if policy.secret_value is not None:
        matched = credentials_match(context.header_credential, policy.secret_value)
        return AccessDecision(
            allowed=matched,
            code="allowed_api_key" if matched else "api_key_invalid",
        )
    if not policy.allow_unauthenticated_loopback:
        return AccessDecision(allowed=False, code="api_auth_not_configured")
    if context.forwarded_headers_present:
        return AccessDecision(allowed=False, code="forwarded_request_rejected")
    if not direct_peer_is_loopback(context.direct_peer):
        return AccessDecision(allowed=False, code="api_auth_not_configured")
    if not authority_is_explicit_loopback(context.authority_host):
        return AccessDecision(allowed=False, code="local_authority_required")
    return AccessDecision(allowed=True, code="allowed_loopback")


def _decode_header(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1")


def _selected_header(
    headers: Sequence[tuple[bytes, bytes]],
    name: str,
    *,
    duplicate_value: str | None = None,
) -> str | None:
    values = [
        _decode_header(value)
        for raw_name, value in headers
        if raw_name.decode("latin-1").lower() == name
    ]
    if len(values) != 1:
        return duplicate_value if len(values) > 1 else None
    return values[0]


def _forwarded_headers_present(headers: Sequence[tuple[bytes, bytes]]) -> bool:
    return any(
        raw_name.decode("latin-1").lower() in FORWARDED_IDENTITY_HEADERS
        for raw_name, _value in headers
    )


def _direct_peer(scope: Mapping[str, object]) -> str | None:
    client = scope.get("client")
    if not isinstance(client, (tuple, list)) or not client:
        return None
    host = client[0]
    return host if isinstance(host, str) else None


def _query_credential_present(query_string: bytes) -> bool:
    component_start = 0
    while component_start <= len(query_string):
        component_end = query_string.find(b"&", component_start)
        if component_end == -1:
            component_end = len(query_string)
        separator = query_string.find(b"=", component_start, component_end)
        key_end = component_end if separator == -1 else separator
        if key_end - component_start <= _MAX_ENCODED_QUERY_KEY_BYTES:
            encoded_key = query_string[component_start:key_end]
            if unquote_to_bytes(encoded_key) == b"api_key":
                return True
        if component_end == len(query_string):
            return False
        component_start = component_end + 1
    return False


def _build_access_context(
    *,
    transport: Literal["http", "websocket"],
    scope: Mapping[str, object],
) -> RequestAccessContext:
    headers = scope.get("headers", [])
    if not isinstance(headers, list):
        headers = list(headers) if isinstance(headers, tuple) else []
    return RequestAccessContext(
        transport=transport,
        direct_peer=_direct_peer(scope),
        authority_host=_selected_header(headers, "host"),
        origin=_selected_header(
            headers,
            "origin",
            duplicate_value=_DUPLICATE_ORIGIN,
        ),
        forwarded_headers_present=_forwarded_headers_present(headers),
        header_credential=_selected_header(headers, "x-api-key"),
        query_credential_present=(
            _query_credential_present(scope.get("query_string", b""))
            if transport == "websocket"
            and isinstance(scope.get("query_string", b""), bytes)
            else False
        ),
    )


def build_http_access_context(request: Request) -> RequestAccessContext:
    return _build_access_context(transport="http", scope=request.scope)


def build_websocket_access_context(websocket: WebSocket) -> RequestAccessContext:
    return _build_access_context(transport="websocket", scope=websocket.scope)
