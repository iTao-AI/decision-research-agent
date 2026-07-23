from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from agent.provider_observability import emit_protocol_validation


_ALIGNMENT_INVALID = "deepseek_reasoning_message_alignment_invalid"
_REASONING_MISSING = "deepseek_reasoning_content_missing"


class DeepSeekReasoningProtocolError(ValueError):
    """Bounded local failure for incomplete DeepSeek thinking history."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _thinking_enabled(extra_body: object) -> bool:
    if not isinstance(extra_body, dict):
        return False
    thinking = extra_body.get("thinking")
    return (
        isinstance(thinking, dict)
        and str(thinking.get("type", "")).lower() == "enabled"
    )


def _thinking_mode(extra_body: object) -> str:
    return "enabled" if _thinking_enabled(extra_body) else "disabled"


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
