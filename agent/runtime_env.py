"""Canonical-first environment compatibility for runtime configuration."""
from __future__ import annotations

import os
from threading import RLock
import warnings


_MISSING = object()
_WARNED_LEGACY_KEYS: set[str] = set()
_WARNING_LOCK = RLock()


def resolve_env(
    canonical_key: str,
    legacy_key: str,
    *,
    default: str | None = None,
) -> str | None:
    """Resolve a canonical key before its deprecated alias."""
    canonical = os.environ.get(canonical_key, _MISSING)
    if canonical is not _MISSING:
        if legacy_key in os.environ:
            _warn_once(
                legacy_key,
                f"{legacy_key} is deprecated and ignored because {canonical_key} is set",
            )
        return canonical

    legacy = os.environ.get(legacy_key, _MISSING)
    if legacy is _MISSING:
        return default

    _warn_once(legacy_key, f"{legacy_key} is deprecated; use {canonical_key}")
    return legacy


def _warn_once(legacy_key: str, message: str) -> None:
    # Keep these semantics aligned with the standalone Tool Client resolver.
    with _WARNING_LOCK:
        if legacy_key in _WARNED_LEGACY_KEYS:
            return
        try:
            warnings.warn(message, FutureWarning, stacklevel=3)
        except FutureWarning:
            # Deprecation visibility must not turn legacy configuration into
            # a startup failure under PYTHONWARNINGS=error.
            pass
        finally:
            _WARNED_LEGACY_KEYS.add(legacy_key)


def _reset_warning_state_for_tests() -> None:
    """Reset warning deduplication for tests; production code must not call it."""
    with _WARNING_LOCK:
        _WARNED_LEGACY_KEYS.clear()
