from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Literal

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import model_validator

from agent.provider_observability import emit_protocol_validation


_ALIGNMENT_INVALID = "deepseek_reasoning_message_alignment_invalid"
_REASONING_MISSING = "deepseek_reasoning_content_missing"
_THINKING_MODE_INVALID = "deepseek_thinking_mode_invalid"
_THINKING_DISABLED_ALIASES = frozenset(
    {"disabled", "off", "none", "false"}
)

DeepSeekThinkingMode = Literal["enabled", "disabled"]


class DeepSeekThinkingConfigurationError(ValueError):
    """Bounded local failure for an unsupported DeepSeek thinking mode."""

    def __init__(self) -> None:
        self.code = _THINKING_MODE_INVALID
        super().__init__(self.code)


def normalize_deepseek_thinking_mode(
    value: object | None,
) -> DeepSeekThinkingMode:
    """Return the one canonical DeepSeek thinking mode or fail closed."""

    if value is None or value == "enabled":
        return "enabled"
    if isinstance(value, str) and value in _THINKING_DISABLED_ALIASES:
        return "disabled"
    raise DeepSeekThinkingConfigurationError


def canonical_deepseek_extra_body(extra_body: object) -> dict[str, Any]:
    """Preserve provider options while making thinking explicit and canonical."""

    if extra_body is None:
        normalized: dict[str, Any] = {}
    elif isinstance(extra_body, Mapping):
        normalized = copy.deepcopy(dict(extra_body))
    else:
        raise DeepSeekThinkingConfigurationError

    thinking = normalized.get("thinking")
    if thinking is None:
        configured_mode = None
    elif isinstance(thinking, Mapping):
        configured_mode = thinking.get("type")
    else:
        raise DeepSeekThinkingConfigurationError

    normalized["thinking"] = {
        "type": normalize_deepseek_thinking_mode(configured_mode)
    }
    return normalized


def deepseek_thinking_mode(extra_body: object) -> DeepSeekThinkingMode:
    """Read effective thinking state through the shared canonical parser."""

    return canonical_deepseek_extra_body(extra_body)["thinking"]["type"]


class DeepSeekReasoningProtocolError(ValueError):
    """Bounded local failure for incomplete DeepSeek thinking history."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _thinking_enabled(extra_body: object) -> bool:
    return deepseek_thinking_mode(extra_body) == "enabled"


def _thinking_mode(extra_body: object) -> str:
    return deepseek_thinking_mode(extra_body)


def _original_has_tool_calls(message: object) -> bool:
    if not isinstance(message, AIMessage):
        return False
    return bool(
        message.tool_calls
        or message.invalid_tool_calls
        or message.additional_kwargs.get("tool_calls")
    )


def _serialized_has_tool_calls(message: object) -> bool:
    return (
        isinstance(message, dict)
        and message.get("role") == "assistant"
        and isinstance(message.get("tool_calls"), list)
        and bool(message["tool_calls"])
    )


class DeepSeekThinkingChatModel(ChatDeepSeek):
    """ChatDeepSeek with the required thinking/tool request round trip."""

    model_role: Literal["primary", "fallback", "single"] = "single"

    @model_validator(mode="before")
    @classmethod
    def _normalize_thinking_configuration(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        normalized["extra_body"] = canonical_deepseek_extra_body(
            normalized.get("extra_body")
        )
        return normalized

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        original_messages = self._convert_input(input_).to_messages()
        historical_tool_call_messages = sum(
            1
            for message in original_messages
            if _original_has_tool_calls(message)
        )
        validated_messages = 0
        payload = super()._get_request_payload(
            input_,
            stop=stop,
            **kwargs,
        )

        if not _thinking_enabled(self.extra_body):
            return payload

        serialized_messages = payload.get("messages")
        if (
            not isinstance(serialized_messages, list)
            or len(serialized_messages) != len(original_messages)
        ):
            emit_protocol_validation(
                model_role=self.model_role,
                thinking_mode=_thinking_mode(self.extra_body),
                outcome="rejected",
                reason=_ALIGNMENT_INVALID,
                historical_tool_call_messages=historical_tool_call_messages,
                validated_messages=validated_messages,
            )
            raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)

        for original, serialized in zip(
            original_messages,
            serialized_messages,
            strict=True,
        ):
            original_has_tools = _original_has_tool_calls(original)
            serialized_has_tools = _serialized_has_tool_calls(serialized)
            if original_has_tools != serialized_has_tools:
                emit_protocol_validation(
                    model_role=self.model_role,
                    thinking_mode=_thinking_mode(self.extra_body),
                    outcome="rejected",
                    reason=_ALIGNMENT_INVALID,
                    historical_tool_call_messages=(
                        historical_tool_call_messages
                    ),
                    validated_messages=validated_messages,
                )
                raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)
            if not serialized_has_tools:
                continue
            if not isinstance(original, AIMessage):
                emit_protocol_validation(
                    model_role=self.model_role,
                    thinking_mode=_thinking_mode(self.extra_body),
                    outcome="rejected",
                    reason=_ALIGNMENT_INVALID,
                    historical_tool_call_messages=(
                        historical_tool_call_messages
                    ),
                    validated_messages=validated_messages,
                )
                raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)

            reasoning_content = original.additional_kwargs.get(
                "reasoning_content"
            )
            if (
                not isinstance(reasoning_content, str)
                or not reasoning_content.strip()
            ):
                emit_protocol_validation(
                    model_role=self.model_role,
                    thinking_mode=_thinking_mode(self.extra_body),
                    outcome="rejected",
                    reason=_REASONING_MISSING,
                    historical_tool_call_messages=(
                        historical_tool_call_messages
                    ),
                    validated_messages=validated_messages,
                )
                raise DeepSeekReasoningProtocolError(_REASONING_MISSING)

            serialized["reasoning_content"] = reasoning_content
            validated_messages += 1

        if historical_tool_call_messages:
            emit_protocol_validation(
                model_role=self.model_role,
                thinking_mode="enabled",
                outcome="valid",
                historical_tool_call_messages=historical_tool_call_messages,
                validated_messages=validated_messages,
            )

        return payload
