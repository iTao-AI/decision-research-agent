# DeepSeek Provider Protocol Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Keep this
> implementation serial because dependency identity, provider construction,
> request serialization, wrappers, and framework composition share one
> contract.

**Goal:** Route DeepSeek models through the official LangChain DeepSeek
integration and preserve DeepSeek thinking-mode `reasoning_content` across
tool-call turns without changing application authority or running a live
provider.

**Architecture:** Add `langchain-deepseek==1.1.0`, introduce a narrow
`ChatDeepSeek` subclass that restores only the missing request-side
`reasoning_content`, and select that leaf for `deepseek-*` model identifiers.
Add a closed local telemetry sink plus LangChain tags/metadata for optional
LangSmith tracing. Keep `CapabilityAwareChatModel`, `FallbackChatModel`,
DeepAgents, and the application-owned result/Evidence lifecycle unchanged.

**Tech Stack:** Python 3.11, LangChain 1.3.10, `langchain-core` 1.4.8,
`langchain-openai` 1.3.2, `langchain-deepseek` 1.1.0, DeepAgents 0.6.11,
LangGraph 1.2.6, Pydantic 2.13.4, pytest 9.0.3, Docker.

## Global Constraints

- Start from the approved spec branch containing
  `docs/superpowers/specs/2026-07-23-deepseek-provider-protocol-closure-design.md`.
- Preserve `VERSION=0.1.5`; do not prepare or publish a release.
- Add `langchain-deepseek>=1.1.0` to `requirements.txt` and pin
  `langchain-deepseek==1.1.0` in `constraints.txt`.
- DeepSeek model identifiers begin with `deepseek-` and must never silently
  initialize through `model_provider="openai"`.
- DeepSeek configuration precedence is
  `DEEPSEEK_API_KEY` over `OPENAI_API_KEY` and `DEEPSEEK_API_BASE` over
  `OPENAI_BASE_URL`.
- Non-DeepSeek model identifiers retain the current OpenAI-compatible path.
- Preserve default model identifiers `deepseek-v4-pro` and
  `deepseek-v4-flash`.
- Preserve automatic tool selection with thinking enabled by omitting the
  provider `tool_choice` parameter. Preserve explicit `none` or forced
  selection on dual-mode V4 by disabling thinking on an independent model
  copy; fixed-thinking legacy aliases fail before transport instead of
  contradicting their model identity.
- Preserve every historical assistant tool-call message's exact non-empty
  `reasoning_content`; missing, invalid, or unalignable protocol state fails
  before transport.
- Do not log or persist raw reasoning, messages, tool arguments, serialized
  payloads, credentials, or secret-derived values.
- Local provider telemetry is limited to the approved event registry and
  closed fields. Fallback logs may include only the exception class name, not
  exception text or traceback.
- DeepSeek LangChain runs use only the approved provider/model-role/protocol
  tags and metadata. They do not add a new trace transport.
- Preserve the bounded-live lifecycle's privacy boundary:
  `LANGSMITH_TRACING=false`, hidden inputs/outputs, and no LangSmith API key.
  Do not query remote traces or make LangSmith a correctness gate.
- Do not access the configured LangSmith key or run a remote LangSmith smoke.
  Actual trace upload remains a separately authorized post-merge operation.
- Do not change prompts, tools, researcher policy, call budgets, retries,
  API, database, Evidence, artifacts, failure taxonomy, diagnostic receipt
  schemas, review, publication, delivery, frontend, CI workflow, migrations,
  `VERSION`, or release metadata.
- Do not run `observe-live`, a provider/model/search call, credential access,
  or live Evidence publication.
- Do not modify or clean the protected bounded-live evidence worktree.
- Use TDD for every behavior task and create one focused local commit per
  task.
- Stop before editing if implementation evidence requires a prohibited scope.

---

## Pre-Execution Gate

- [ ] **Step 1: Re-read current authority and verify identities**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git merge-base HEAD origin/main
git log --oneline --decorate -5
git worktree list --porcelain
```

Expected:

- the task worktree is clean;
- HEAD contains the approved spec and mechanically landed plan;
- merge base is the reviewed `origin/main`;
- the primary and protected bounded-live worktrees are clean; and
- no implementation commit exists yet.

- [ ] **Step 2: Record the implementation allowlist**

Create a shell variable for review commands:

```bash
BASE_SHA="$(git merge-base HEAD origin/main)"
printf '%s\n' "$BASE_SHA"
```

The approved implementation surface is:

```text
agent/deepseek_chat_model.py
agent/llm.py
requirements.txt
constraints.txt
scripts/report_runtime_versions.py
tests/unit/test_deepseek_chat_model.py
tests/unit/test_llm_config.py
tests/unit/test_deployment_preflight.py
tests/unit/test_runtime_versions.py
tests/integration/test_harness_execution.py
.env.example
docs/reference/external-services.md
CHANGELOG.md
tests/unit/test_documentation_contracts.py
tests/unit/test_release_metadata.py
tests/unit/test_release_presentation_contracts.py
```

The spec and plan documents already on the branch are expected historical
inputs. Any newly discovered need outside the implementation surface must be
reported before editing.

## Task 1: Lock The Official DeepSeek Integration

**Files:**

- Modify: `requirements.txt`
- Modify: `constraints.txt`
- Modify: `scripts/report_runtime_versions.py`
- Modify: `tests/unit/test_deployment_preflight.py`
- Modify: `tests/unit/test_runtime_versions.py`

**Interfaces:**

- Consumes: the repository's direct-requirement and exact-constraint policy.
- Produces: installed `langchain_deepseek.ChatDeepSeek` version `1.1.0` and
  runtime-version reporting for `langchain-deepseek`.

- [ ] **Step 1: Add a failing dependency contract**

Append the following helper and test to
`tests/unit/test_deployment_preflight.py`:

```python
def _requirements_by_name(path: Path) -> dict[str, Requirement]:
    requirements: dict[str, Requirement] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        requirements[requirement.name] = requirement
    return requirements


def test_official_deepseek_integration_is_declared_and_pinned():
    declared = _requirements_by_name(PROJECT_ROOT / "requirements.txt")
    locked = _requirements_by_name(PROJECT_ROOT / "constraints.txt")

    assert "langchain-deepseek" in declared
    assert ">=1.1.0" in str(declared["langchain-deepseek"].specifier)
    assert str(locked["langchain-deepseek"].specifier) == "==1.1.0"
```

Extend `tests/unit/test_runtime_versions.py` with:

```python
def test_official_deepseek_integration_is_reported():
    assert "langchain-deepseek" in RUNTIME_PACKAGES
```

- [ ] **Step 2: Run the dependency contracts and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python3.11 -m pytest -q \
  tests/unit/test_deployment_preflight.py::test_official_deepseek_integration_is_declared_and_pinned \
  tests/unit/test_runtime_versions.py::test_official_deepseek_integration_is_reported
```

Expected: two assertion failures because the dependency and runtime-report
entry do not exist.

- [ ] **Step 3: Add the direct requirement and exact constraint**

Under the LLM service section of `requirements.txt`, add:

```text
langchain-deepseek>=1.1.0   # DeepSeek 官方 LangChain 适配
```

In alphabetical position in `constraints.txt`, add:

```text
langchain-deepseek==1.1.0
```

In `scripts/report_runtime_versions.py`, update the tuple to include the new
runtime package:

```python
RUNTIME_PACKAGES = (
    "deepagents",
    "langchain",
    "langchain-core",
    "langchain-deepseek",
    "langgraph",
    "langgraph-checkpoint-sqlite",
    "langsmith",
    "fastapi",
    "pydantic",
)
```

- [ ] **Step 4: Build the task-owned locked Python environment**

Run:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --no-deps -r constraints.txt
```

Expected: installation succeeds and does not modify tracked files.

- [ ] **Step 5: Verify the selected wheel identity**

Run:

```bash
WHEEL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dra-deepseek-wheel-check.XXXXXX")"
chmod 700 "$WHEEL_DIR"
trap 'find "$WHEEL_DIR" -type f -delete; rmdir "$WHEEL_DIR"' EXIT
.venv/bin/python -m pip download \
  --no-deps \
  --only-binary=:all: \
  --dest "$WHEEL_DIR" \
  langchain-deepseek==1.1.0
shasum -a 256 \
  "$WHEEL_DIR/langchain_deepseek-1.1.0-py3-none-any.whl"
find "$WHEEL_DIR" -type f -delete
rmdir "$WHEEL_DIR"
trap - EXIT
```

Expected SHA-256:

```text
14813cb413a97a5cce95118da253cfd64dce50537b7381b7c5d0ecf11d2a7032
```

- [ ] **Step 6: Run the GREEN dependency and runtime-version tests**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_deployment_preflight.py \
  tests/unit/test_runtime_versions.py
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/report_runtime_versions.py
```

Expected:

- both test files pass;
- the JSON report contains
  `"langchain-deepseek": "1.1.0"`; and
- no production credential is read.

- [ ] **Step 7: Review and commit Task 1**

Run:

```bash
git diff --check
git diff -- \
  requirements.txt \
  constraints.txt \
  scripts/report_runtime_versions.py \
  tests/unit/test_deployment_preflight.py \
  tests/unit/test_runtime_versions.py
git add \
  requirements.txt \
  constraints.txt \
  scripts/report_runtime_versions.py \
  tests/unit/test_deployment_preflight.py \
  tests/unit/test_runtime_versions.py
git commit -m "build: add official DeepSeek integration"
```

## Task 2: Preserve DeepSeek Thinking State Across Tool Calls

**Files:**

- Create: `agent/deepseek_chat_model.py`
- Create: `tests/unit/test_deepseek_chat_model.py`

**Interfaces:**

- Consumes:
  `langchain_deepseek.ChatDeepSeek._get_request_payload(LanguageModelInput,
  stop, **kwargs) -> dict`.
- Produces:
  `DeepSeekThinkingChatModel`, a drop-in `ChatDeepSeek` subclass, and
  `DeepSeekReasoningProtocolError.code`. The leaf also carries the closed
  `model_role=primary|fallback|single` diagnostic identity used by Task 4.

- [ ] **Step 1: Write the failing request-round-trip tests**

Create `tests/unit/test_deepseek_chat_model.py` with the following fixtures and
core RED cases:

```python
from __future__ import annotations

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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


def test_injects_reasoning_content_for_every_historical_tool_call():
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


@pytest.mark.parametrize("reasoning", [None, "", "   ", 7])
def test_missing_or_invalid_reasoning_fails_before_transport(reasoning):
    model = _model()
    additional_kwargs = (
        {} if reasoning is None else {"reasoning_content": reasoning}
    )
    message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "query")],
        additional_kwargs=additional_kwargs,
    )

    with pytest.raises(DeepSeekReasoningProtocolError) as raised:
        model._get_request_payload([HumanMessage(content="research"), message])

    assert raised.value.code == "deepseek_reasoning_content_missing"
    assert "query" not in str(raised.value)


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
```

Add tests in the same file for:

```python
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

    assert raised.value.code == "deepseek_reasoning_message_alignment_invalid"
    assert "private-reasoning" not in str(raised.value)
    assert "secret-query" not in str(raised.value)
```

When implementing the mutation test, save the concrete `ChatDeepSeek` method
before monkeypatching it so the replacement does not recursively call itself.

- [ ] **Step 2: Run the new test file and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_deepseek_chat_model.py
```

Expected: collection fails because
`agent.deepseek_chat_model` does not exist.

- [ ] **Step 3: Implement the narrow adapter**

Create `agent/deepseek_chat_model.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek


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
            raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)

        for original, serialized in zip(
            original_messages,
            serialized_messages,
            strict=True,
        ):
            original_has_tools = _original_has_tool_calls(original)
            serialized_has_tools = _serialized_has_tool_calls(serialized)
            if original_has_tools != serialized_has_tools:
                raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)
            if not serialized_has_tools:
                continue
            if not isinstance(original, AIMessage):
                raise DeepSeekReasoningProtocolError(_ALIGNMENT_INVALID)

            reasoning_content = original.additional_kwargs.get(
                "reasoning_content"
            )
            if (
                not isinstance(reasoning_content, str)
                or not reasoning_content.strip()
            ):
                raise DeepSeekReasoningProtocolError(_REASONING_MISSING)

            serialized["reasoning_content"] = reasoning_content

        return payload
```

Do not add logging in Task 2. Task 4 adds only the approved closed telemetry
after the protocol behavior is independently GREEN.

- [ ] **Step 4: Add official response and streaming preservation tests**

Extend `tests/unit/test_deepseek_chat_model.py` with:

```python
from langchain_core.messages import AIMessageChunk
from openai.types.chat import ChatCompletion


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
```

The locked `AIMessageChunk.__add__` path aggregates
`additional_kwargs`, `tool_call_chunks`, and parsed `tool_calls`; constructing
the final `AIMessage` from `aggregated.tool_calls` therefore exercises the
official chunk parser and aggregation path before the adapter request
serializer. The async case goes through the official inherited `_astream`
implementation with a local fake completions client, so no provider request is
made.

- [ ] **Step 5: Run the complete adapter unit matrix**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_deepseek_chat_model.py
```

Expected: all tests pass with no network access.

- [ ] **Step 6: Verify bounded exceptions and commit Task 2**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py
git diff --check
git diff -- \
  agent/deepseek_chat_model.py \
  tests/unit/test_deepseek_chat_model.py
git add \
  agent/deepseek_chat_model.py \
  tests/unit/test_deepseek_chat_model.py
git commit -m "feat(agent): preserve DeepSeek reasoning round trip"
```

## Task 3: Route DeepSeek Models Through The Native Provider

**Files:**

- Modify: `agent/llm.py`
- Modify: `tests/unit/test_llm_config.py`

**Interfaces:**

- Consumes:
  `DeepSeekThinkingChatModel(**kwargs) -> BaseChatModel`.
- Produces:
  `_is_deepseek_model(model_name: str) -> bool`,
  `_create_leaf_model(model_name, model_role, callbacks) -> BaseChatModel`,
  and existing `create_llm_model()` wrapper composition.

- [ ] **Step 1: Replace the stale provider expectation with RED routing tests**

Update the environment reset list in `_reload_llm` to include:

```python
"DEEPSEEK_API_KEY",
"DEEPSEEK_API_BASE",
```

Split test capture into `deepseek_calls` and `openai_calls`. Patch
`agent.deepseek_chat_model.DeepSeekThinkingChatModel` before reloading
`agent.llm`:

```python
def fake_deepseek_model(**kwargs):
    deepseek_calls.append(kwargs)
    return FakeChatModel(
        model_name=kwargs["model"],
        extra_body=kwargs.get("extra_body"),
    )


def fake_init_chat_model(**kwargs):
    openai_calls.append(kwargs)
    return FakeChatModel(model_name=kwargs["model"])
```

Replace the default-provider assertions with:

```python
def test_default_models_use_official_deepseek_provider(monkeypatch):
    llm, deepseek_calls, openai_calls = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "legacy-test-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
        },
    )

    assert [call["model"] for call in deepseek_calls] == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ]
    assert [call["model_role"] for call in deepseek_calls] == [
        "primary",
        "fallback",
    ]
    assert openai_calls == []
    for call in deepseek_calls:
        assert "model_provider" not in call
        assert call["api_key"] == "legacy-test-key"
        assert call["base_url"] == "https://api.deepseek.com"
        assert call["reasoning_effort"] == "max"
        assert call["extra_body"] == {"thinking": {"type": "enabled"}}

    assert isinstance(llm.model, llm.FallbackChatModel)
    assert isinstance(llm.model.primary, llm.CapabilityAwareChatModel)
    assert isinstance(llm.model.fallback, llm.CapabilityAwareChatModel)
```

Add precedence and non-DeepSeek tests:

```python
def test_deepseek_specific_configuration_wins(monkeypatch):
    _, deepseek_calls, openai_calls = _reload_llm(
        monkeypatch,
        {
            "DEEPSEEK_API_KEY": "deepseek-test-key",
            "DEEPSEEK_API_BASE": "https://deepseek.example/v1",
            "OPENAI_API_KEY": "legacy-test-key",
            "OPENAI_BASE_URL": "https://legacy.example/v1",
        },
    )

    assert openai_calls == []
    assert {
        (call["api_key"], call["base_url"])
        for call in deepseek_calls
    } == {("deepseek-test-key", "https://deepseek.example/v1")}


def test_non_deepseek_model_keeps_openai_compatible_path(monkeypatch):
    _, deepseek_calls, openai_calls = _reload_llm(
        monkeypatch,
        {
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_FALLBACK_MODEL": "none",
            "OPENAI_API_KEY": "openai-test-key",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        },
    )

    assert deepseek_calls == []
    assert len(openai_calls) == 1
    assert openai_calls[0]["model"] == "gpt-4.1-mini"
    assert openai_calls[0]["model_provider"] == "openai"


def test_deepseek_initialization_failure_does_not_fall_back_to_openai(
    monkeypatch,
):
    llm, _, openai_calls = _reload_llm(
        monkeypatch,
        {
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_FALLBACK_MODEL": "none",
            "OPENAI_API_KEY": "openai-test-key",
        },
    )

    with (
        patch.object(
            llm,
            "DeepSeekThinkingChatModel",
            side_effect=ImportError("integration unavailable"),
        ),
        pytest.raises(ImportError, match="integration unavailable"),
    ):
        llm._create_leaf_model("deepseek-v4-pro", "primary", [])

    assert len(openai_calls) == 1
```

Adjust existing `_reload_llm` return unpacking throughout the test file without
changing the assertions unrelated to provider construction.

- [ ] **Step 2: Run provider selection tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_llm_config.py \
  -k "official_deepseek_provider or deepseek_specific_configuration or non_deepseek_model or initialization_failure"
```

Expected: failures show DeepSeek still uses the generic OpenAI initializer and
the provider-specific precedence/helper is absent.

- [ ] **Step 3: Implement provider-specific construction**

In `agent/llm.py`, import the new leaf:

```python
from agent.deepseek_chat_model import DeepSeekThinkingChatModel
```

Add the provider family helper next to the existing DeepSeek v4 helper:

```python
_DEEPSEEK_PREFIX = "deepseek-"


def _is_deepseek_model(model_name: str) -> bool:
    return model_name.lower().startswith(_DEEPSEEK_PREFIX)
```

Replace `_model_kwargs` with:

```python
def _model_kwargs(
    model_name: str,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model_name,
        "callbacks": callbacks or [],
    }

    if _is_deepseek_model(model_name):
        base_url = (
            _env_value("DEEPSEEK_API_BASE")
            or _env_value("OPENAI_BASE_URL")
        )
        api_key = (
            _env_value("DEEPSEEK_API_KEY")
            or _env_value("OPENAI_API_KEY")
        )
    else:
        kwargs["model_provider"] = "openai"
        base_url = _env_value("OPENAI_BASE_URL")
        api_key = _env_value("OPENAI_API_KEY")

    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    reasoning_effort = _reasoning_effort(model_name)
    if (
        reasoning_effort
        and reasoning_effort.lower()
        not in {"none", "off", "disabled", "false"}
    ):
        kwargs["reasoning_effort"] = reasoning_effort

    thinking_mode = _thinking_mode(model_name)
    if (
        thinking_mode
        and thinking_mode.lower()
        not in {"none", "off", "disabled", "false"}
    ):
        kwargs["extra_body"] = {
            "thinking": {"type": thinking_mode}
        }

    return kwargs


def _create_leaf_model(
    model_name: str,
    model_role: str,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> BaseChatModel:
    kwargs = _model_kwargs(model_name, callbacks)
    if _is_deepseek_model(model_name):
        return DeepSeekThinkingChatModel(
            **kwargs,
            model_role=model_role,
        )
    return init_chat_model(**kwargs)
```

Update both primary and fallback construction sites:

```python
wrapped=_create_leaf_model(primary_model, "primary", callbacks)
```

and:

```python
wrapped=_create_leaf_model(fallback_model, "fallback", callbacks)
```

Do not catch `ImportError`, `ValidationError`, or provider initialization
errors in `_create_leaf_model`.

- [ ] **Step 4: Preserve wrapper and capability behavior**

Update only the test harness and stale provider assertions in
`tests/unit/test_llm_config.py`. Retain the existing tests for:

- callback attachment;
- fallback invocation;
- fallback logging;
- forced tool choice;
- automatic/no tool choice;
- independent copied `extra_body`;
- model role;
- profile metadata;
- structured-output capability metadata; and
- secret/tool schema logging boundaries.

Add an explicit primary/fallback leaf test:

```python
def test_primary_and_fallback_receive_the_same_provider_policy(monkeypatch):
    llm, deepseek_calls, _ = _reload_llm(
        monkeypatch,
        {
            "DEEPSEEK_API_KEY": "deepseek-test-key",
            "DEEPSEEK_API_BASE": "https://deepseek.example/v1",
        },
    )

    assert isinstance(llm.model, llm.FallbackChatModel)
    assert [call["model"] for call in deepseek_calls] == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ]
    assert {
        (
            call["api_key"],
            call["base_url"],
            call["extra_body"]["thinking"]["type"],
        )
        for call in deepseek_calls
    } == {
        (
            "deepseek-test-key",
            "https://deepseek.example/v1",
            "enabled",
        )
    }
```

Extend the message imports in the same file with `HumanMessage` and
`ToolMessage`, and import
`DeepSeekReasoningProtocolError` plus `DeepSeekThinkingChatModel`. Add a
fallback strictness and privacy regression:

```python
def test_fallback_keeps_protocol_validation_strict_and_bounded(
    monkeypatch,
    caplog,
):
    llm, _, _ = _reload_llm(
        monkeypatch,
        {
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_FALLBACK_MODEL": "none",
            "OPENAI_API_KEY": "openai-test-key",
        },
    )

    def strict_leaf(model_name: str) -> DeepSeekThinkingChatModel:
        return DeepSeekThinkingChatModel(
            model=model_name,
            api_key="provider-test-key",
            base_url="https://api.deepseek.com",
            max_retries=0,
            extra_body={"thinking": {"type": "enabled"}},
        )

    model = llm.FallbackChatModel(
        primary=llm.CapabilityAwareChatModel(
            wrapped=strict_leaf("deepseek-v4-pro"),
            model_role="primary",
        ),
        fallback=llm.CapabilityAwareChatModel(
            wrapped=strict_leaf("deepseek-v4-flash"),
            model_role="fallback",
        ),
    )
    messages = [
        HumanMessage(content="sensitive-user-content"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "internet_search",
                    "args": {"query": "sensitive-query"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="sensitive-tool-result",
            tool_call_id="call-1",
            name="internet_search",
        ),
    ]

    with (
        caplog.at_level("WARNING"),
        pytest.raises(DeepSeekReasoningProtocolError) as raised,
    ):
        model.invoke(messages)

    assert raised.value.code == "deepseek_reasoning_content_missing"
    assert "sensitive-user-content" not in caplog.text
    assert "sensitive-query" not in caplog.text
    assert "sensitive-tool-result" not in caplog.text
```

Both leaves must reject before transport. The primary wrapper may log the
bounded protocol category, but it must not log message, tool, reasoning, or
credential values.

Also extend the existing Pydantic import with `BaseModel` and add an explicit
structured-output composition regression:

```python
class StructuredAnswer(BaseModel):
    answer: str


def test_structured_output_composition_remains_available(monkeypatch):
    llm, _, _ = _reload_llm(
        monkeypatch,
        {
            "LLM_MODEL": "gpt-4.1-mini",
            "LLM_FALLBACK_MODEL": "none",
            "OPENAI_API_KEY": "openai-test-key",
        },
    )
    primary_leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}},
    )
    fallback_leaf = ToolBindingChatModel(
        model_name="deepseek-v4-flash",
        extra_body={"thinking": {"type": "enabled"}},
    )
    primary = llm.CapabilityAwareChatModel(
        wrapped=primary_leaf,
        model_role="primary",
    )
    fallback = llm.CapabilityAwareChatModel(
        wrapped=fallback_leaf,
        model_role="fallback",
    )
    model = llm.FallbackChatModel(
        primary=primary,
        fallback=fallback,
    )

    structured = model.with_structured_output(StructuredAnswer)

    assert structured is not None
    assert primary.last_bound_model is not primary_leaf
    assert fallback.last_bound_model is not fallback_leaf
    assert primary.last_bound_model.extra_body == {
        "thinking": {"type": "disabled"}
    }
    assert fallback.last_bound_model.extra_body == {
        "thinking": {"type": "disabled"}
    }
```

This locks the existing capability-wrapper behavior: the framework-native
structured-output path remains available, and its forced tool choice operates
on independent thinking-disabled copies rather than mutating the configured
DeepSeek leaves.

- [ ] **Step 5: Run the full LLM and adapter matrix**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
LANGSMITH_TRACING=false \
LANGSMITH_API_KEY= \
.venv/bin/python -m pytest -q \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py \
  tests/unit/test_token_tracking.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git diff --check
git diff -- agent/llm.py tests/unit/test_llm_config.py
git add agent/llm.py tests/unit/test_llm_config.py
git commit -m "feat(agent): route DeepSeek through native provider"
```

## Task 4: Add Safe Provider Observability And LangSmith Readiness

**Files:**

- Create: `agent/provider_observability.py`
- Modify: `agent/deepseek_chat_model.py`
- Modify: `agent/llm.py`
- Create: `tests/unit/test_provider_observability.py`
- Modify: `tests/unit/test_deepseek_chat_model.py`
- Modify: `tests/unit/test_llm_config.py`

**Interfaces:**

- Consumes:
  `DeepSeekThinkingChatModel.model_role`, DeepSeek validation codes, and the
  existing LangChain `tags`/`metadata` fields on chat models.
- Produces:
  `emit_provider_selected(...)`,
  `emit_protocol_validation(...)`, and
  `emit_fallback_activated(...)`; a closed local event registry; and
  LangSmith-ready provider tags/metadata that remain inert while tracing is
  disabled.

- [ ] **Step 1: Write failing closed-event and redaction tests**

Create `tests/unit/test_provider_observability.py`:

```python
from __future__ import annotations

import logging

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
```

Add mutation cases that pass an unsupported role, thinking mode, protocol
reason, provider family, or binding. Each must produce no log record and must
not raise into the caller.

- [ ] **Step 2: Run the telemetry tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_provider_observability.py
```

Expected: collection fails because `agent.provider_observability` does not
exist.

- [ ] **Step 3: Implement the closed local telemetry sink**

Create `agent/provider_observability.py`:

```python
from __future__ import annotations

import logging
import re
from typing import Literal


logger = logging.getLogger(__name__)

PROVIDER_PROTOCOL = "deepseek-reasoning-content-v1"
_MAX_COUNT = 10_000
_MODEL_ROLES = frozenset({"primary", "fallback", "single"})
_THINKING_MODES = frozenset({"enabled", "disabled"})
_PROVIDER_FAMILIES = frozenset({"deepseek", "openai-compatible", "unknown"})
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
```

The module accepts no message, reasoning, tool payload, endpoint, credential,
serialized request, or free-form exception text argument. Invalid diagnostic
inputs are dropped; they never change runtime control flow.

- [ ] **Step 4: Instrument validation without changing its authority**

In `agent/deepseek_chat_model.py`, import:

```python
from agent.provider_observability import emit_protocol_validation
```

Add:

```python
def _thinking_mode(extra_body: object) -> str:
    return "enabled" if _thinking_enabled(extra_body) else "disabled"
```

At the start of `_get_request_payload`, after obtaining
`original_messages`, calculate:

```python
historical_tool_call_messages = sum(
    1 for message in original_messages if _original_has_tool_calls(message)
)
validated_messages = 0
```

For each `_ALIGNMENT_INVALID` or `_REASONING_MISSING` branch, emit the rejected
event immediately before raising:

```python
emit_protocol_validation(
    model_role=self.model_role,
    thinking_mode=_thinking_mode(self.extra_body),
    outcome="rejected",
    reason=code,
    historical_tool_call_messages=historical_tool_call_messages,
    validated_messages=validated_messages,
)
raise DeepSeekReasoningProtocolError(code)
```

After assigning each exact `reasoning_content`, increment:

```python
validated_messages += 1
```

Before returning a thinking-enabled payload with at least one historical
tool-call message, emit:

```python
emit_protocol_validation(
    model_role=self.model_role,
    thinking_mode="enabled",
    outcome="valid",
    historical_tool_call_messages=historical_tool_call_messages,
    validated_messages=validated_messages,
)
```

Do not emit a protocol-validation event for a thinking-disabled request or a
history with no assistant tool-call message.

- [ ] **Step 5: Add LangSmith-ready tags/metadata and safe fallback events**

In `agent/llm.py`, import:

```python
from agent.provider_observability import (
    PROVIDER_PROTOCOL,
    emit_fallback_activated,
    emit_provider_selected,
)
```

Add:

```python
def _provider_family(model: BaseChatModel) -> str:
    return (
        "deepseek"
        if _is_deepseek_model(_model_name(model))
        else "openai-compatible"
    )


def _deepseek_observability(
    *,
    model_role: str,
    thinking_mode: str,
) -> dict[str, object]:
    return {
        "tags": [
            "provider:deepseek",
            f"model-role:{model_role}",
            f"protocol:{PROVIDER_PROTOCOL}",
        ],
        "metadata": {
            "provider_family": "deepseek",
            "model_role": model_role,
            "provider_protocol": PROVIDER_PROTOCOL,
            "thinking_mode": thinking_mode,
        },
    }
```

In `_create_leaf_model`, when the model is DeepSeek, merge the exact
observability configuration before construction:

```python
thinking_mode = _configured_thinking_mode(model_name)
kwargs.update(
    _deepseek_observability(
        model_role=model_role,
        thinking_mode=thinking_mode,
    )
)
emit_provider_selected(
    model_role=model_role,
    thinking_mode=thinking_mode,
)
return DeepSeekThinkingChatModel(
    **kwargs,
    model_role=model_role,
)
```

Define `_configured_thinking_mode` next to `_thinking_mode`:

```python
def _configured_thinking_mode(model_name: str) -> str:
    value = _thinking_mode(model_name)
    return (
        "enabled"
        if value is not None
        and value.lower() not in {"none", "off", "disabled", "false"}
        else "disabled"
    )
```

In `create_llm_model`, compute the same configuration per role and pass it to
the outer `CapabilityAwareChatModel`:

```python
primary_observability = (
    _deepseek_observability(
        model_role="primary",
        thinking_mode=_configured_thinking_mode(primary_model),
    )
    if _is_deepseek_model(primary_model)
    else {}
)
model = CapabilityAwareChatModel(
    wrapped=_create_leaf_model(primary_model, "primary", callbacks),
    model_role="primary",
    callbacks=callbacks or [],
    **primary_observability,
)
```

For the final `FallbackChatModel`, use the primary safe tags/metadata and add
only:

```python
fallback_wrapper_metadata = {
    **dict(primary_observability.get("metadata", {})),
    "fallback_configured": True,
}
fallback_wrapper_tags = [
    *list(primary_observability.get("tags", [])),
    "fallback:configured",
]
```

The single-model wrapper keeps the single role configuration. This ensures the
actual graph-invoked model run carries only the safe configuration. Do not add
`@traceable` or a second tracing transport.

Replace `FallbackRunnable.__init__.warning_message` with the two
already-classified string fields `primary_provider_family` and
`fallback_provider_family`.
`FallbackChatModel.bind_tools()` computes them from `self.primary` and
`self.fallback` before producing the bound runnables and passes them into
`FallbackRunnable`.

Replace all four raw fallback log calls in `FallbackRunnable` and
`FallbackChatModel`. The direct `FallbackChatModel` branches call:

```python
emit_fallback_activated(
    primary_provider_family=_provider_family(self.primary),
    fallback_provider_family=_provider_family(self.fallback),
    error=exc,
    binding="direct",
)
```

The tool-bound `FallbackRunnable` branches call:

```python
emit_fallback_activated(
    primary_provider_family=self.primary_provider_family,
    fallback_provider_family=self.fallback_provider_family,
    error=exc,
    binding="tools",
)
```

Then invoke the same configured fallback as before. Do not call
`logger.warning(..., exc_info=True)` and do not log `str(exc)`.

- [ ] **Step 6: Add integration-facing metadata and privacy regressions**

In `tests/unit/test_llm_config.py`, assert that the captured primary/fallback
DeepSeek constructor calls contain:

```python
assert deepseek_calls[0]["model_role"] == "primary"
assert deepseek_calls[1]["model_role"] == "fallback"
assert deepseek_calls[0]["tags"] == [
    "provider:deepseek",
    "model-role:primary",
    "protocol:deepseek-reasoning-content-v1",
]
assert deepseek_calls[0]["metadata"] == {
    "provider_family": "deepseek",
    "model_role": "primary",
    "provider_protocol": "deepseek-reasoning-content-v1",
    "thinking_mode": "enabled",
}
```

Add equivalent fallback assertions and prove that the final graph-invoked
wrapper retains the safe tags/metadata. Add direct and tool-bound fallback
tests whose primary raises
`RuntimeError("sensitive-provider-response")`; assert the fallback returns,
the event contains `error_type=RuntimeError`, `record.exc_info is None`, and
the sensitive string is absent.

In `tests/unit/test_deepseek_chat_model.py`, use `caplog` to prove:

- valid history emits the exact valid event and counts;
- missing reasoning emits the bounded rejected code and counts;
- raw reasoning, user content, tool arguments, and tool results never appear;
- monkeypatching `agent.provider_observability.logger.log` to raise cannot
  change a valid return or the exact `DeepSeekReasoningProtocolError`; and
- no test needs `LANGSMITH_API_KEY` or sets `LANGSMITH_TRACING=true`.

- [ ] **Step 7: Run the observability matrix**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false \
  LANGSMITH_API_KEY= .venv/bin/python -m pytest -q \
  tests/unit/test_provider_observability.py \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py \
  tests/unit/test_token_tracking.py
```

Expected: all tests pass, no network is used, and no remote trace exists.

- [ ] **Step 8: Review and commit Task 4**

Run:

```bash
git diff --check
git diff -- \
  agent/provider_observability.py \
  agent/deepseek_chat_model.py \
  agent/llm.py \
  tests/unit/test_provider_observability.py \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py
git add \
  agent/provider_observability.py \
  agent/deepseek_chat_model.py \
  agent/llm.py \
  tests/unit/test_provider_observability.py \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py
git commit -m "feat(agent): add safe provider observability"
```

## Task 5: Prove Native DeepAgents Tool-Call Composition

**Files:**

- Modify: `tests/integration/test_harness_execution.py`
- Modify: `tests/unit/test_deepseek_chat_model.py`

**Interfaces:**

- Consumes:
  `DeepSeekThinkingChatModel`, DeepAgents `create_deep_agent`, native
  `write_file`, `ResearchExecutionService`, and the existing application
  observer.
- Produces:
  provider-free proof that official response parsing plus the request adapter
  completes `model -> tool -> model -> canonical report`.

- [ ] **Step 1: Add a scripted official-response DeepSeek test model**

In `tests/integration/test_harness_execution.py`, add imports:

```python
from copy import deepcopy

from openai.types.chat import ChatCompletion

from agent.deepseek_chat_model import DeepSeekThinkingChatModel
```

Add this provider-free fake transport:

```python
class ScriptedDeepSeekWriteModel(DeepSeekThinkingChatModel):
    call_count: int = 0
    request_payloads: list[dict[str, Any]] = Field(default_factory=list)

    def _response(self) -> ChatCompletion:
        if self.call_count == 1:
            message = {
                "role": "assistant",
                "content": "",
                "reasoning_content": "bounded-tool-reasoning",
                "tool_calls": [
                    {
                        "id": "call-write-report",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": (
                                '{"file_path":'
                                '"/workspace/research-report.md",'
                                '"content":"# Canonical report\\n"}'
                            ),
                        },
                    }
                ],
            }
            finish_reason = "tool_calls"
        else:
            message = {
                "role": "assistant",
                "content": "Canonical report written.",
            }
            finish_reason = "stop"

        return ChatCompletion.model_validate(
            {
                "id": f"completion-{self.call_count}",
                "object": "chat.completion",
                "created": 0,
                "model": self.model_name,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish_reason,
                        "message": message,
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        payload = self._get_request_payload(
            messages,
            stop=stop,
            **kwargs,
        )
        self.request_payloads.append(deepcopy(payload))
        self.call_count += 1
        return self._create_chat_result(self._response())

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )
```

This class replaces transport only. It continues to use the official
`ChatDeepSeek` response parser and the production request serializer.

- [ ] **Step 2: Add the real DeepAgents canonical-completion test**

Append:

```python
@pytest.mark.asyncio
async def test_deepseek_tool_turn_round_trips_reasoning_to_canonical_report(
    tmp_path,
):
    model = ScriptedDeepSeekWriteModel(
        model="deepseek-v4-pro",
        api_key="provider-test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        extra_body={"thinking": {"type": "enabled"}},
    )
    service = ResearchExecutionService(
        harness=_real_deepagents_harness(
            model,
            completion_guard=False,
        ),
        project_root=tmp_path,
    )

    outcome = await service.execute(
        "Produce the canonical report.",
        "thread-deepseek-protocol-1",
        run_id="run-deepseek-protocol-1",
        segment_id="segment-deepseek-protocol-1",
        profile_id="generic",
    )

    assert model.call_count == 2
    assert outcome.report_candidate == ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Canonical report\n",
    )
    assistant_messages = [
        message
        for message in model.request_payloads[1]["messages"]
        if message["role"] == "assistant" and message.get("tool_calls")
    ]
    assert len(assistant_messages) == 1
    assert (
        assistant_messages[0]["reasoning_content"]
        == "bounded-tool-reasoning"
    )
```

- [ ] **Step 3: Add the synchronous composition path**

Use the same model with the existing real graph helper and invoke the graph
synchronously. Add:

```python
def test_deepseek_sync_graph_round_trips_reasoning():
    model = ScriptedDeepSeekWriteModel(
        model="deepseek-v4-pro",
        api_key="provider-test-key",
        base_url="https://api.deepseek.com",
        max_retries=0,
        extra_body={"thinking": {"type": "enabled"}},
    )
    backend = CompositeBackend(default=StateBackend(), routes={})
    graph = create_deep_agent(
        model=model,
        tools=[],
        system_prompt="Write the requested canonical report.",
        middleware=[],
        subagents=[],
        permissions=list(build_filesystem_permissions()),
        backend=backend,
        context_schema=ResearchRuntimeContext,
        name="deepseek-protocol-sync",
    )
    context = ResearchRuntimeContext(
        thread_id="thread-deepseek-sync-1",
        run_id="run-deepseek-sync-1",
        segment_id="segment-deepseek-sync-1",
        profile_id="generic",
    )

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Produce the canonical report.",
                }
            ]
        },
        context=context,
    )

    assert model.call_count == 2
    assert result["files"]["/workspace/research-report.md"]["content"] == (
        "# Canonical report\n"
    )
    assert (
        model.request_payloads[1]["messages"][1]["reasoning_content"]
        == "bounded-tool-reasoning"
    )
```

- [ ] **Step 4: Add privacy regression coverage**

In `tests/unit/test_deepseek_chat_model.py`, add:

```python
def test_protocol_failure_does_not_log_reasoning_or_tool_arguments(caplog):
    model = _model()
    message = AIMessage(
        content="",
        tool_calls=[_tool_call("call-1", "sensitive-query")],
    )

    with pytest.raises(DeepSeekReasoningProtocolError):
        model._get_request_payload(
            [HumanMessage(content="sensitive-user-content"), message]
        )

    assert "sensitive-query" not in caplog.text
    assert "sensitive-user-content" not in caplog.text
```

The real async `ResearchExecutionService` graph test in Step 2 and the real
synchronous `create_deep_agent` graph test in Step 3 provide the approved
async/sync framework composition coverage. The adapter unit tests separately
lock request serialization and official streaming aggregation.

- [ ] **Step 5: Run the framework composition RED/GREEN matrix**

Before the production adapter/routing is complete, the new composition test
must fail because the second request lacks `reasoning_content`. After Tasks 2
and 3, run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py \
  tests/integration/test_harness_execution.py
```

Expected: all tests pass, including the real DeepAgents tool turn and
canonical report.

- [ ] **Step 6: Run related profile and result regressions**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_profile_middleware.py \
  tests/unit/test_deepagents_harness.py \
  tests/unit/test_run_result.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_run_result_api.py
```

Expected: all tests pass with no changed call budget, middleware ordering,
result contract, or application authority.

- [ ] **Step 7: Commit Task 5**

Run:

```bash
git diff --check
git diff -- \
  tests/unit/test_deepseek_chat_model.py \
  tests/integration/test_harness_execution.py
git add \
  tests/unit/test_deepseek_chat_model.py \
  tests/integration/test_harness_execution.py
git commit -m "test(agent): prove DeepSeek tool-call protocol"
```

## Task 6: Publish Configuration And Provider Boundaries

**Files:**

- Modify: `.env.example`
- Modify: `docs/reference/external-services.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_release_metadata.py`
- Modify: `tests/unit/test_release_presentation_contracts.py`

**Interfaces:**

- Consumes: the implemented provider selection, compatibility aliases, and
  provider-free proof boundary, local telemetry registry, and LangSmith-ready
  tags/metadata.
- Produces: public-neutral configuration and Unreleased documentation matching
  executable behavior.

- [ ] **Step 1: Add failing documentation contracts**

In `tests/unit/test_documentation_contracts.py`, add:

```python
def test_deepseek_provider_protocol_documentation_matches_runtime():
    env_example = (
        PROJECT_ROOT / ".env.example"
    ).read_text(encoding="utf-8")
    reference = (
        PROJECT_ROOT / "docs/reference/external-services.md"
    ).read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY=" in env_example
    assert "DEEPSEEK_API_BASE=https://api.deepseek.com" in env_example
    assert "DEEPSEEK_API_KEY" in reference
    assert "DEEPSEEK_API_BASE" in reference
    assert "OPENAI_API_KEY" in reference
    assert "OPENAI_BASE_URL" in reference
    assert "official LangChain DeepSeek integration" in reference
    assert "reasoning_content" in reference
    assert "provider protocol state" in reference
    assert "not Evidence" in reference
    assert "does not prove a live provider result" in reference
    assert "## Optional LangSmith Diagnostics" in reference
    assert "deepseek_provider_selected" in reference
    assert "deepseek_reasoning_protocol_validated" in reference
    assert "deepseek_reasoning_protocol_rejected" in reference
    assert "model_fallback_activated" in reference
    assert "LANGSMITH_TRACING=false" in reference
    assert "LANGSMITH_HIDE_INPUTS=true" in reference
    assert "LANGSMITH_HIDE_OUTPUTS=true" in reference
    assert "bounded-live" in reference
    assert "separate operator authorization" in reference
```

In `tests/unit/test_release_metadata.py`, add:

```python
def test_unreleased_records_deepseek_provider_protocol_closure() -> None:
    changelog = _read(PROJECT_ROOT / "CHANGELOG.md")
    unreleased = changelog.split("## [Unreleased]", 1)[1].split(
        "## [0.1.5]",
        1,
    )[0]

    assert "### DeepSeek provider protocol" in unreleased
    assert "langchain-deepseek==1.1.0" in unreleased
    assert "reasoning_content" in unreleased
    assert "bounded local provider-protocol telemetry" in unreleased
    assert "remote tracing disabled" in unreleased
    assert "No live provider result" in unreleased
    assert "## [0.1.5]" not in unreleased
```

Update the required provider label in
`tests/unit/test_release_presentation_contracts.py` from:

```python
"OpenAI-compatible provider (default DeepSeek)"
```

to:

```python
"Official DeepSeek provider integration"
```

- [ ] **Step 2: Run documentation tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
```

Expected: failures identify the old OpenAI-compatible description, missing
preferred environment variables, and missing Unreleased section.

- [ ] **Step 3: Update `.env.example`**

Replace the LLM header block with:

```text
# LLM Configuration
# DeepSeek models prefer the provider-specific variables. The OPENAI_ names
# remain supported compatibility aliases for existing local environments.
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_API_KEY=
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=
LLM_MODEL=deepseek-v4-pro
LLM_FALLBACK_MODEL=deepseek-v4-flash
LLM_REASONING_EFFORT=max
LLM_THINKING_MODE=enabled
# Legacy compatibility: used only when LLM_MODEL is not set
# LLM_QWEN_MAX=deepseek-v4-pro
```

Do not insert a real credential.

- [ ] **Step 4: Update the external-services reference**

Change the provider row label to:

```text
Official DeepSeek provider integration
```

Replace the current `OpenAI-Compatible Provider` section with a
`DeepSeek And OpenAI-Compatible Providers` section that states all of the
following:

```text
- `deepseek-*` model identifiers use the official LangChain DeepSeek
  integration.
- DeepSeek configuration prefers `DEEPSEEK_API_BASE` and
  `DEEPSEEK_API_KEY`; `OPENAI_BASE_URL` and `OPENAI_API_KEY` remain
  compatibility aliases.
- Non-DeepSeek identifiers retain the OpenAI-compatible provider path.
- Thinking-mode assistant tool calls preserve the exact
  `reasoning_content` as provider protocol state for the next request.
- Provider protocol state is not Evidence, application state, review,
  publication, or delivery authority.
- Explicit `none` and forced tool selection use the existing
  thinking-disabled model copy for dual-mode V4; fixed-thinking legacy aliases
  fail before transport. Automatic tool selection keeps thinking enabled by
  omitting the provider `tool_choice` parameter.
- Provider-free tests cover the protocol adapter and real DeepAgents
  composition. This does not prove a live provider result, research quality,
  cost, or production readiness.
```

Bind the approved 120-second client request timeout explicitly on official
primary and fallback leaf models, including sync/async clients and
tool-binding copies. Retain the existing provider/model fallback non-claim;
the timeout is not a provider SLA.

Retain `deepseek-chat` as the fixed non-thinking alias and
`deepseek-reasoner` as the fixed thinking alias of `deepseek-v4-flash` only
through their documented 2026-07-24 15:59 UTC retirement boundary. Reject
explicit mode conflicts before construction and do not recommend either
deprecated identifier in `.env.example`.

Add:

```markdown
## Optional LangSmith Diagnostics

- Local structured logs use only `deepseek_provider_selected`,
  `deepseek_reasoning_protocol_validated`,
  `deepseek_reasoning_protocol_rejected`, and
  `model_fallback_activated`. They contain bounded provider/protocol facts,
  counts, codes, and exception class names; they never contain reasoning,
  message/tool payloads, credentials, provider response bodies, exception
  text, or tracebacks.
- LangChain and DeepAgents already support automatic LangSmith tracing.
  DeepSeek model runs carry only the allowlisted provider family, model role,
  provider protocol, and thinking-mode tags/metadata added by this change.
- Checked-in configuration keeps `LANGSMITH_TRACING=false`,
  `LANGSMITH_HIDE_INPUTS=true`, and `LANGSMITH_HIDE_OUTPUTS=true`; no key is
  committed.
- The bounded-live producer continues to require tracing disabled, hidden
  inputs/outputs, and an empty LangSmith key.
- A privacy-first remote trace smoke is a separate operator-authorized action.
  It is not required for provider correctness and does not own ResearchRun,
  Evidence, review, publication, or delivery truth.
```

- [ ] **Step 5: Add the Unreleased changelog section**

Under `## [Unreleased]`, before the existing bounded-live section, add:

```markdown
### DeepSeek provider protocol

- Routed `deepseek-*` primary and fallback models through the official
  LangChain DeepSeek integration, pinned as `langchain-deepseek==1.1.0`.
- Added a narrow provider adapter that preserves exact non-empty
  `reasoning_content` across thinking-mode tool-call turns and fails before
  transport when required protocol state is missing or unalignable.
- Preserved the OpenAI-compatible path for non-DeepSeek models, existing
  credential aliases, forced-tool-choice compatibility, call budgets, and
  application-owned Evidence and delivery authority.
- Added bounded local provider-protocol telemetry and privacy-safe
  LangSmith-ready tags/metadata while keeping remote tracing disabled for
  required and bounded-live verification.
- No live provider result, research-quality result, cost result, consumer
  acceptance, deployment, or release claim is made by this provider-free
  change.
```

- [ ] **Step 6: Run documentation and release contracts**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
python scripts/final_presentation_audit.py
python scripts/check_canonical_identity.py --root .
```

Expected: all tests pass and both audits report zero violations.

- [ ] **Step 7: Commit Task 6**

Run:

```bash
git diff --check
git diff -- \
  .env.example \
  docs/reference/external-services.md \
  CHANGELOG.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
git add \
  .env.example \
  docs/reference/external-services.md \
  CHANGELOG.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
git commit -m "docs(agent): publish DeepSeek provider boundary"
```

## Task 7: Integrated Verification And Handoff

**Files:**

- Verify all branch changes.
- Do not create a verification-only tracked file.

**Interfaces:**

- Consumes: Tasks 1–6 and the approved design.
- Produces: a clean local branch ready for authoritative branch-diff review.

- [ ] **Step 1: Run the focused provider and framework matrix**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
LANGSMITH_TRACING=false \
LANGSMITH_API_KEY= \
.venv/bin/python -m pytest -q \
  tests/unit/test_provider_observability.py \
  tests/unit/test_deepseek_chat_model.py \
  tests/unit/test_llm_config.py \
  tests/unit/test_deployment_preflight.py \
  tests/unit/test_runtime_versions.py \
  tests/unit/test_token_tracking.py \
  tests/unit/test_profile_middleware.py \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_run_result_api.py
```

Expected: all tests pass.

- [ ] **Step 2: Run all provider-free deterministic gates**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python \
  scripts/bounded_live_producer_proof.py check
```

Expected: every command exits zero; deterministic comparison gates report
valid/match according to their existing output contracts.

- [ ] **Step 3: Run the complete non-Docker backend suite**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python -m pytest -q -m "not docker"
```

Expected: all selected tests pass. Record the exact passed/deselected/skipped
counts from the command; do not reuse counts from another HEAD.

- [ ] **Step 4: Record Docker ownership and capacity before the required lane**

Run read-only inventory commands:

```bash
df -h .
docker system df
docker ps -a --format '{{.ID}} {{.Names}} {{.Status}}'
docker compose ls --all
docker image ls --digests
docker volume ls
docker network ls
docker buildx du
```

Record:

- host filesystem availability;
- Docker VM/build cache availability;
- containers and Compose projects;
- images;
- volumes;
- networks; and
- which resources, if any, are owned by this task.

Do not run a broad prune, delete an ownership-unknown resource, restart Docker,
or change daemon/BuildKit configuration.

- [ ] **Step 5: Run the required Docker authority lane**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
LANGSMITH_TRACING=false \
LANGSMITH_API_KEY= \
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
.venv/bin/python -m pytest -q -m docker
```

Expected: all required Docker tests pass using the updated exact locked
dependency set.

Afterward, rerun the inventory commands from Step 4 and remove only resources
whose exact task ownership is established by the existing test lifecycle.
Retain shared base images and BuildKit cache unless the approved lifecycle
already removes a task-owned image by exact identity.

- [ ] **Step 6: Run final documentation and authority audits**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGSMITH_API_KEY= \
  .venv/bin/python -m pytest -q \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
python scripts/final_presentation_audit.py
python scripts/check_canonical_identity.py --root .
git diff --check origin/main..HEAD
```

Expected: all tests and audits pass.

- [ ] **Step 7: Audit exact branch scope**

Run:

```bash
git diff --name-status origin/main..HEAD
git diff --stat origin/main..HEAD
git status --short --branch
```

Then verify prohibited areas have no implementation diff:

```bash
git diff --quiet origin/main..HEAD -- \
  api \
  migrations \
  frontend \
  .github/workflows \
  VERSION \
  docs/releases \
  docs/evidence
```

Expected: the prohibited-diff command exits zero.

Scan added lines without printing secrets. Construct repository-private and
unfinished markers from fragments so this public plan does not contain the
literal values it rejects:

```bash
ADDED_DIFF="$(mktemp "${TMPDIR:-/tmp}/dra-deepseek-added.XXXXXX")"
chmod 600 "$ADDED_DIFF"
trap 'rm -f "$ADDED_DIFF"' EXIT
git diff --unified=0 origin/main..HEAD > "$ADDED_DIFF"
DRA_DEEPSEEK_ADDED_DIFF="$ADDED_DIFF" python - <<'PY'
from pathlib import Path
import os
import re

text = Path(os.environ["DRA_DEEPSEEK_ADDED_DIFF"]).read_text(
    encoding="utf-8"
)
markers = [
    "/" + "Users" + "/",
    "Car" + "eer",
    "Night" + " Voyager",
    "求" + "职",
    "TO" + "DO",
    "T" + "BD",
    "FIX" + "ME",
    "place" + "holder",
]
credential_patterns = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
]
findings = [marker for marker in markers if marker in text]
findings.extend(
    pattern.pattern
    for pattern in credential_patterns
    if pattern.search(text)
)
if findings:
    raise SystemExit(
        "public_or_sensitive_marker_detected:" + ",".join(findings)
    )
PY
rm -f "$ADDED_DIFF"
trap - EXIT
```

Expected: the scanner exits zero and the exact task-owned temporary diff is
removed.

Also confirm no raw reasoning value is present outside synthetic test fixtures:

```bash
git diff --unified=0 origin/main..HEAD | \
  rg -n 'reasoning-one|reasoning-two|parsed-reasoning|streamed-reasoning|bounded-tool-reasoning'
```

Expected: matches occur only in the new provider-free tests and their exact
assertions, never logs, docs claims, runtime constants, or evidence.

- [ ] **Step 8: Perform a targeted read-only review**

Review the integrated diff specifically for:

- use of `ChatDeepSeek` rather than `ChatOpenAI` for `deepseek-*`;
- exact all-history reasoning alignment;
- fail-before-transport behavior;
- no message mutation;
- sync/async/streaming parity;
- effective thinking-disabled copies;
- primary/fallback equivalence;
- config precedence and secret safety;
- exact local event allowlist and bounded fields;
- no raw fallback exception text or traceback;
- safe LangChain tags/metadata on the graph-invoked model;
- no LangSmith key access, remote trace, or tracing correctness dependency;
- no application authority drift; and
- no upstream behavior reimplementation beyond request reinsertion.

If the review finds a concrete issue, reproduce it with a failing test before
editing. Run targeted tests and the complete matrix again after repair. Do not
start a second broad redesign.

- [ ] **Step 9: Produce the terminal implementation report**

The terminal report must include:

- base and final HEAD;
- branch and worktree;
- ordered implementation commits;
- RED-to-GREEN evidence per Task;
- exact changed files and diff stat;
- installed/locked framework versions;
- focused, full non-Docker, deterministic proof, docs, audit, and required
  Docker results;
- Docker before/after inventory and retained resources;
- confirmation that no provider, credential, live Evidence, release, push, PR,
  merge, tag, or deploy occurred;
- confirmation that local provider telemetry used only approved event fields
  and fallback logs did not retain raw exception text;
- remaining framework-upgrade and live-validation risks; and
- confirmation that remote LangSmith tracing remained disabled and was not
  used as correctness or authority, and no LangSmith key was accessed; and
- a request for authoritative branch-diff review.

The worktree must be clean. Do not push, create a PR, merge, release, deploy,
run a provider, or clean the implementation branch/worktree.
