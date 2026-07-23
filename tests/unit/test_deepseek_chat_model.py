from __future__ import annotations

from copy import deepcopy

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    ToolMessage,
)
from openai.types.chat import ChatCompletion

from agent import provider_observability
from agent.deepseek_chat_model import (
    DeepSeekReasoningProtocolError,
    DeepSeekThinkingChatModel,
)


def _tool_call(call_id: str, query: str) -> dict:
    return {
        "name": "internet_search",
        "args": {"query": query},
        "id": call_id,
        "type": "tool_call",
    }


def _model(*, thinking: str = "enabled") -> DeepSeekThinkingChatModel:
    return DeepSeekThinkingChatModel(
        model="deepseek-v4-pro",
        api_key="provider-test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        extra_body={"thinking": {"type": thinking}},
    )


def test_injects_reasoning_content_for_every_historical_tool_call(caplog):
    model = _model()
    messages = [
        HumanMessage(content="research"),
        AIMessage(
            content="",
            tool_calls=[_tool_call("call-1", "first")],
            additional_kwargs={"reasoning_content": "reasoning-one"},
        ),
        ToolMessage(
            content="first result",
            tool_call_id="call-1",
            name="internet_search",
        ),
        AIMessage(
            content="",
            tool_calls=[_tool_call("call-2", "second")],
            additional_kwargs={"reasoning_content": "reasoning-two"},
        ),
        ToolMessage(
            content="second result",
            tool_call_id="call-2",
            name="internet_search",
        ),
    ]
    original = deepcopy(messages)

    with caplog.at_level("INFO"):
        payload = model._get_request_payload(messages)
    assistants = [
        message
        for message in payload["messages"]
        if message["role"] == "assistant" and message.get("tool_calls")
    ]

    assert [message["reasoning_content"] for message in assistants] == [
        "reasoning-one",
        "reasoning-two",
    ]
    assert messages == original
    assert "event=deepseek_reasoning_protocol_validated" in caplog.text
    assert "historical_tool_call_messages=2" in caplog.text
    assert "validated_messages=2" in caplog.text
    assert "reasoning-one" not in caplog.text
    assert "first result" not in caplog.text


@pytest.mark.parametrize("reasoning", [None, "", "   ", 7])
def test_missing_or_invalid_reasoning_fails_before_transport(
    reasoning,
    caplog,
):
    model = _model()
    additional_kwargs = (
        {} if reasoning is None else {"reasoning_content": reasoning}
    )
    message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "query")],
        additional_kwargs=additional_kwargs,
    )

    with (
        caplog.at_level("WARNING"),
        pytest.raises(DeepSeekReasoningProtocolError) as raised,
    ):
        model._get_request_payload(
            [HumanMessage(content="sensitive-user-content"), message]
        )

    assert raised.value.code == "deepseek_reasoning_content_missing"
    assert "query" not in str(raised.value)
    assert "event=deepseek_reasoning_protocol_rejected" in caplog.text
    assert "historical_tool_call_messages=1" in caplog.text
    assert "validated_messages=0" in caplog.text
    assert "sensitive-user-content" not in caplog.text
    assert "query" not in caplog.text


def test_thinking_disabled_does_not_require_or_inject_reasoning():
    model = _model(thinking="disabled")
    message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "query")],
    )

    payload = model._get_request_payload(
        [HumanMessage(content="research"), message]
    )

    assistant = payload["messages"][1]
    assert assistant["tool_calls"]
    assert "reasoning_content" not in assistant


def test_assistant_without_tool_calls_is_not_modified():
    model = _model()
    message = AIMessage(
        content="finished",
        additional_kwargs={"reasoning_content": "not-required"},
    )

    payload = model._get_request_payload(
        [HumanMessage(content="research"), message]
    )

    assert "reasoning_content" not in payload["messages"][1]


def test_alignment_failure_uses_bounded_error(monkeypatch):
    model = _model()
    message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "secret-query")],
        additional_kwargs={"reasoning_content": "private-reasoning"},
    )
    original = DeepSeekThinkingChatModel.__mro__[1]._get_request_payload

    def misaligned(self, input_, *, stop=None, **kwargs):
        payload = original(self, input_, stop=stop, **kwargs)
        payload["messages"] = payload["messages"][:-1]
        return payload

    monkeypatch.setattr(
        DeepSeekThinkingChatModel.__mro__[1],
        "_get_request_payload",
        misaligned,
    )

    with pytest.raises(DeepSeekReasoningProtocolError) as raised:
        model._get_request_payload([HumanMessage(content="research"), message])

    assert (
        raised.value.code
        == "deepseek_reasoning_message_alignment_invalid"
    )
    assert "private-reasoning" not in str(raised.value)
    assert "secret-query" not in str(raised.value)


def _completion_with_reasoning() -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "completion-test",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "parsed-reasoning",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "internet_search",
                                    "arguments": '{"query":"bounded"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
    )


def test_official_non_streaming_parser_preserves_reasoning():
    result = _model()._create_chat_result(_completion_with_reasoning())

    assert (
        result.generations[0].message.additional_kwargs["reasoning_content"]
        == "parsed-reasoning"
    )


def test_official_stream_chunks_aggregate_then_round_trip():
    model = _model()
    raw_chunks = [
        {
            "id": "chunk-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": None,
                    "delta": {
                        "role": "assistant",
                        "reasoning_content": "streamed-",
                    },
                }
            ],
        },
        {
            "id": "chunk-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": None,
                    "delta": {
                        "reasoning_content": "reasoning",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "internet_search",
                                    "arguments": '{"query":"bounded"}',
                                },
                            }
                        ],
                    },
                }
            ],
        },
    ]
    generations = [
        model._convert_chunk_to_generation_chunk(
            chunk,
            AIMessageChunk,
            {},
        )
        for chunk in raw_chunks
    ]
    messages = [
        generation.message
        for generation in generations
        if generation is not None
    ]
    aggregated = messages[0] + messages[1]
    final_message = AIMessage(
        content=aggregated.content,
        additional_kwargs=aggregated.additional_kwargs,
        tool_calls=aggregated.tool_calls,
        invalid_tool_calls=aggregated.invalid_tool_calls,
    )

    payload = model._get_request_payload(
        [HumanMessage(content="research"), final_message]
    )

    assert (
        payload["messages"][1]["reasoning_content"]
        == "streamed-reasoning"
    )


@pytest.mark.asyncio
async def test_official_async_stream_preserves_reasoning_and_tool_calls():
    raw_chunks = [
        {
            "id": "chunk-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": None,
                    "delta": {
                        "role": "assistant",
                        "reasoning_content": "async-",
                    },
                }
            ],
        },
        {
            "id": "chunk-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "delta": {
                        "reasoning_content": "reasoning",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "internet_search",
                                    "arguments": '{"query":"bounded"}',
                                },
                            }
                        ],
                    },
                }
            ],
        },
    ]

    class AsyncChunkStream:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self):
            return None

    class AsyncCompletions:
        def __init__(self, chunks):
            self.chunks = chunks
            self.payload = None

        async def create(self, **payload):
            self.payload = deepcopy(payload)
            return AsyncChunkStream(self.chunks)

    client = AsyncCompletions(raw_chunks)
    model = DeepSeekThinkingChatModel(
        model="deepseek-v4-pro",
        api_key="provider-test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        async_client=client,
        extra_body={"thinking": {"type": "enabled"}},
    )

    streamed = [
        chunk
        async for chunk in model._astream(
            [HumanMessage(content="research")]
        )
    ]
    aggregated = streamed[0].message + streamed[1].message
    final_message = AIMessage(
        content=aggregated.content,
        additional_kwargs=aggregated.additional_kwargs,
        tool_calls=aggregated.tool_calls,
        invalid_tool_calls=aggregated.invalid_tool_calls,
    )
    payload = model._get_request_payload(
        [HumanMessage(content="research"), final_message]
    )

    assert client.payload is not None
    assert client.payload["stream"] is True
    assert (
        payload["messages"][1]["reasoning_content"]
        == "async-reasoning"
    )
    assert payload["messages"][1]["tool_calls"][0]["id"] == "call-1"


def test_observability_failure_cannot_change_protocol_result(monkeypatch):
    model = _model()
    valid_message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "private-query")],
        additional_kwargs={"reasoning_content": "private-reasoning"},
    )

    def fail_log(*args, **kwargs):
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr(provider_observability.logger, "log", fail_log)

    payload = model._get_request_payload(
        [HumanMessage(content="private-user"), valid_message]
    )

    assert payload["messages"][1]["reasoning_content"] == "private-reasoning"

    invalid_message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-2", "private-query")],
    )
    with pytest.raises(DeepSeekReasoningProtocolError) as raised:
        model._get_request_payload(
            [HumanMessage(content="private-user"), invalid_message]
        )

    assert raised.value.code == "deepseek_reasoning_content_missing"
