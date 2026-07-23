from __future__ import annotations

import logging
import re
from typing import Literal


logger = logging.getLogger(__name__)

PROVIDER_PROTOCOL = "deepseek-reasoning-content-v1"
_MAX_COUNT = 10_000
_MODEL_ROLES = frozenset({"primary", "fallback", "single"})
_THINKING_MODES = frozenset({"enabled", "disabled"})
_PROVIDER_FAMILIES = frozenset(
    {"deepseek", "openai-compatible", "unknown"}
)
_PROTOCOL_REASONS = frozenset(
    {
        "deepseek_reasoning_content_missing",
        "deepseek_reasoning_message_alignment_invalid",
    }
)
_BINDINGS = frozenset({"direct", "tools"})
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _bounded_count(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("provider_observation_count_invalid")
    return min(value, _MAX_COUNT)


def _safe_log(level: int, message: str, *args: object) -> None:
    try:
        logger.log(level, message, *args)
    except Exception:
        return


def emit_provider_selected(
    *,
    model_role: Literal["primary", "fallback", "single"],
    thinking_mode: Literal["enabled", "disabled"],
) -> None:
    if model_role not in _MODEL_ROLES or thinking_mode not in _THINKING_MODES:
        return
    _safe_log(
        logging.INFO,
        (
            "event=deepseek_provider_selected "
            "provider_family=deepseek "
            "model_role=%s "
            "thinking_mode=%s "
            "provider_protocol=%s"
        ),
        model_role,
        thinking_mode,
        PROVIDER_PROTOCOL,
    )


def emit_protocol_validation(
    *,
    model_role: Literal["primary", "fallback", "single"],
    thinking_mode: Literal["enabled", "disabled"],
    outcome: Literal["valid", "rejected"],
    historical_tool_call_messages: int,
    validated_messages: int,
    reason: str | None = None,
) -> None:
    try:
        historical = _bounded_count(historical_tool_call_messages)
        validated = _bounded_count(validated_messages)
    except ValueError:
        return
    if (
        model_role not in _MODEL_ROLES
        or thinking_mode not in _THINKING_MODES
        or validated > historical
    ):
        return
    if outcome == "valid":
        if reason is not None or validated != historical:
            return
        event = "deepseek_reasoning_protocol_validated"
        reason_value = "not_applicable"
    elif outcome == "rejected":
        if reason not in _PROTOCOL_REASONS:
            return
        event = "deepseek_reasoning_protocol_rejected"
        reason_value = reason
    else:
        return
    _safe_log(
        logging.INFO if outcome == "valid" else logging.WARNING,
        (
            "event=%s "
            "provider_family=deepseek "
            "model_role=%s "
            "thinking_mode=%s "
            "provider_protocol=%s "
            "outcome=%s "
            "reason=%s "
            "historical_tool_call_messages=%d "
            "validated_messages=%d"
        ),
        event,
        model_role,
        thinking_mode,
        PROVIDER_PROTOCOL,
        outcome,
        reason_value,
        historical,
        validated,
    )


def emit_fallback_activated(
    *,
    primary_provider_family: str,
    fallback_provider_family: str,
    error: Exception,
    binding: Literal["direct", "tools"],
) -> None:
    error_type = type(error).__name__
    if (
        primary_provider_family not in _PROVIDER_FAMILIES
        or fallback_provider_family not in _PROVIDER_FAMILIES
        or binding not in _BINDINGS
        or _ERROR_TYPE.fullmatch(error_type) is None
    ):
        return
    _safe_log(
        logging.WARNING,
        (
            "event=model_fallback_activated "
            "primary_provider_family=%s "
            "fallback_provider_family=%s "
            "binding=%s "
            "error_type=%s"
        ),
        primary_provider_family,
        fallback_provider_family,
        binding,
        error_type,
    )
