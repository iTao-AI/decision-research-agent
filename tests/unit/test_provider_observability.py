from __future__ import annotations

import logging

import pytest

from agent.provider_observability import (
    emit_fallback_activated,
    emit_protocol_validation,
    emit_provider_selected,
)


def test_provider_selection_event_is_closed_and_safe(caplog):
    with caplog.at_level(logging.INFO):
        emit_provider_selected(
            model_role="primary",
            thinking_mode="enabled",
        )

    assert (
        "event=deepseek_provider_selected "
        "provider_family=deepseek "
        "model_role=primary "
        "thinking_mode=enabled "
        "provider_protocol=deepseek-reasoning-content-v1"
    ) in caplog.text


def test_protocol_validation_events_contain_only_counts_and_codes(caplog):
    with caplog.at_level(logging.INFO):
        emit_protocol_validation(
            model_role="primary",
            thinking_mode="enabled",
            outcome="valid",
            historical_tool_call_messages=2,
            validated_messages=2,
        )
        emit_protocol_validation(
            model_role="fallback",
            thinking_mode="enabled",
            outcome="rejected",
            reason="deepseek_reasoning_content_missing",
            historical_tool_call_messages=2,
            validated_messages=1,
        )

    assert "event=deepseek_reasoning_protocol_validated" in caplog.text
    assert "event=deepseek_reasoning_protocol_rejected" in caplog.text
    assert "historical_tool_call_messages=2" in caplog.text
    assert "validated_messages=1" in caplog.text
    assert "deepseek_reasoning_content_missing" in caplog.text


def test_fallback_event_does_not_log_exception_text_or_traceback(caplog):
    error = RuntimeError("sensitive-provider-response")

    with caplog.at_level(logging.WARNING):
        emit_fallback_activated(
            primary_provider_family="deepseek",
            fallback_provider_family="deepseek",
            error=error,
            binding="tools",
        )

    assert "event=model_fallback_activated" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "sensitive-provider-response" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    ("function", "kwargs"),
    [
        (
            emit_provider_selected,
            {"model_role": "other", "thinking_mode": "enabled"},
        ),
        (
            emit_provider_selected,
            {"model_role": "primary", "thinking_mode": "other"},
        ),
        (
            emit_protocol_validation,
            {
                "model_role": "primary",
                "thinking_mode": "enabled",
                "outcome": "rejected",
                "reason": "raw-provider-reason",
                "historical_tool_call_messages": 1,
                "validated_messages": 0,
            },
        ),
        (
            emit_fallback_activated,
            {
                "primary_provider_family": "private-provider",
                "fallback_provider_family": "deepseek",
                "error": RuntimeError("private"),
                "binding": "direct",
            },
        ),
        (
            emit_fallback_activated,
            {
                "primary_provider_family": "deepseek",
                "fallback_provider_family": "deepseek",
                "error": RuntimeError("private"),
                "binding": "other",
            },
        ),
    ],
)
def test_unsupported_observation_is_dropped(function, kwargs, caplog):
    with caplog.at_level(logging.INFO):
        function(**kwargs)

    assert caplog.records == []
