"""Pure admission policy for publishable bounded-live source URLs."""
from __future__ import annotations

from collections.abc import Mapping
import ipaddress
import re
from urllib.parse import urlsplit


MAX_PUBLISHABLE_SOURCE_URL_BYTES = 2048
MAX_SEARCH_RESULTS = 100

_DOMAIN_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _has_invalid_percent_escape(value: str) -> bool:
    index = 0
    while True:
        index = value.find("%", index)
        if index < 0:
            return False
        if (
            index + 2 >= len(value)
            or value[index + 1] not in _HEX_DIGITS
            or value[index + 2] not in _HEX_DIGITS
        ):
            return True
        decoded = int(value[index + 1 : index + 3], 16)
        if decoded < 0x20 or decoded == 0x7F:
            return True
        index += 3


def is_publishable_source_url(value: object) -> bool:
    """Return True only for a bounded-live publishable public source URL."""
    if type(value) is not str or not value:
        return False
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        return False
    if (
        len(encoded) > MAX_PUBLISHABLE_SOURCE_URL_BYTES
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x20 for character in value)
        or "\x7f" in value
        or value.endswith((".", ",", ";", ":", "!", "?"))
        or _has_invalid_percent_escape(value)
    ):
        return False

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (ValueError, UnicodeError):
        return False
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        return False

    expected_authority = hostname if port is None else f"{hostname}:{port}"
    if parsed.netloc != expected_authority:
        return False
    if hostname.endswith(
        (".local", ".internal", ".localhost")
    ) or not _DOMAIN_RE.fullmatch(hostname):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return False


def filter_publishable_search_response(payload: object) -> dict[str, object]:
    """Return a fresh bounded response containing only admitted result rows."""
    if not isinstance(payload, Mapping):
        return {"results": []}
    results = payload.get("results")
    if type(results) is not list or len(results) > MAX_SEARCH_RESULTS:
        return {"results": []}

    return {
        "results": [
            dict(row)
            for row in results
            if isinstance(row, Mapping)
            and is_publishable_source_url(row.get("url"))
        ]
    }
