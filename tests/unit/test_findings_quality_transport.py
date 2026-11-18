from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
import json

import httpx
import pytest

from scripts import findings_quality_transport as live


APPROVAL = "a" * 64
MESSAGES = [{"role": "user", "content": "Frozen public passage"}]
FILE_TOOL = {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object"}}}


def budget(**overrides):
    return live.ChatBudget(**{
        "max_requests": 3,
        "max_input_tokens": 8_000,
        "max_output_tokens": 300,
        "max_input_tokens_per_request": 4_000,
        "max_output_tokens_per_request": 100,
        "max_elapsed_seconds": 30,
        "max_estimated_microusd": 8_000,
        **overrides,
    })


def reply(*, usage=True, message=None, finish_reason="stop"):
    body = {
        "id": "chatcmpl-scripted",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-5.4-mini-2026-03-17",
        "service_tier": "default",
        "choices": [{
            "index": 0,
            "message": message or {"role": "assistant", "content": "validated answer", "refusal": None},
            "finish_reason": finish_reason,
            "logprobs": None,
        }],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}
    return httpx.Response(200, json=body)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chat(receipt_dir, handler, **overrides):
    return live.BoundedChat(**{
        "opt_in": True,
        "approval_id": APPROVAL,
        "proposal_sha256": APPROVAL,
        "budget": budget(),
        "receipt_dir": receipt_dir,
        "transport": httpx.MockTransport(handler),
        "key_loader": lambda: "scripted-credential",
        **overrides,
    })


def unexpected(_=None):
    pytest.fail("unexpected transport or credential read")


async def ask(adapter, request_id="case.1", *, kind="judge", messages=MESSAGES, tools=None, validate=None):
    return await adapter.complete(
        kind=kind,
        request_id=request_id,
        messages=messages,
        tools=tools,
        validate=validate or (lambda message: message["content"]),
    )


@pytest.mark.parametrize("authorization", [{"opt_in": False}, {"approval_id": "b" * 64}])
def test_requires_explicit_matching_opt_in_before_credentials_or_transport(tmp_path, authorization):
    async def run():
        async with chat(tmp_path / "run", unexpected, key_loader=unexpected, **authorization):
            pytest.fail("unauthorized run opened")

    with pytest.raises(live.LiveCallError, match="not_authorized"):
        asyncio.run(run())
    assert list(tmp_path.iterdir()) == []


def test_requests_use_pinned_model_and_only_allowlisted_receipt_fields(tmp_path):
    def respond(request):
        assert request.method == "POST"
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer scripted-credential"
        body = json.loads(request.content)
        assert body == {
            "messages": MESSAGES,
            "model": "gpt-5.4-mini-2026-03-17",
            "reasoning_effort": "none",
            "service_tier": "default",
            "store": False,
            "max_completion_tokens": 100,
            "stream": False,
        }
        return reply()

    async def run():
        async with chat(tmp_path / "run", respond) as adapter:
            return await ask(adapter)

    assert asyncio.run(run()) == "validated answer"
    result = read(tmp_path / "run" / "0001-result.json")
    assert result["execution_mode"] == "scripted"
    assert result["status"] == "success"
    assert result["http_status"] == 200
    assert result["provider_response_id"] == "chatcmpl-scripted"
    assert result["input_tokens"] == 12
    assert result["output_tokens"] == 4
    assert result["observed_estimated_microusd"] == 27
    assert result["request_id"] == "case.1"
    for receipt in (tmp_path / "run").iterdir():
        raw = receipt.read_text()
        assert "scripted-credential" not in raw
        assert "Frozen public passage" not in raw
        assert "validated answer" not in raw


def test_generation_passes_local_function_tools_and_preserves_missing_usage(tmp_path):
    def respond(request):
        assert json.loads(request.content)["tools"] == [FILE_TOOL]
        return reply(
            usage=False,
            message={
                "role": "assistant", "content": None, "refusal": None,
                "tool_calls": [{
                    "id": "call_write", "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"},
                }],
            },
            finish_reason="tool_calls",
        )

    async def run():
        async with chat(tmp_path / "run", respond) as adapter:
            return await ask(
                adapter, kind="generation", tools=[FILE_TOOL],
                validate=lambda message: message["tool_calls"][0]["function"]["name"],
            )

    assert asyncio.run(run()) == "write_file"
    result = read(tmp_path / "run" / "0001-result.json")
    assert result["kind"] == "generation"
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["observed_estimated_microusd"] is None


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"max_input_tokens_per_request": 100}, "input_per_request"),
        ({"max_input_tokens": 100, "max_input_tokens_per_request": 100}, "input_per_request"),
        ({"max_estimated_microusd": 1}, "estimated_cost"),
    ],
)
def test_preflight_budget_refuses_to_load_key_or_send(tmp_path, limits, reason):
    async def run():
        async with chat(tmp_path / "run", unexpected, budget=budget(**limits), key_loader=unexpected) as adapter:
            await ask(adapter)

    with pytest.raises(live.LiveCallError, match="budget_exhausted"):
        asyncio.run(run())
    blocked = read(tmp_path / "run" / "0001-blocked.json")
    assert blocked["reason"] == reason
    assert not (tmp_path / "run" / "0001-started.json").exists()


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"max_requests": 1}, "request_count"),
        ({"max_output_tokens": 100}, "output_total"),
        ({"max_input_tokens": 600, "max_input_tokens_per_request": 600}, "input_total"),
    ],
)
def test_exhaustion_preserves_success_and_blocks_second_send(tmp_path, limits, reason):
    seen = []

    def respond(request):
        seen.append(request)
        return reply(usage=False)

    async def run():
        async with chat(tmp_path / "run", respond, budget=budget(**limits)) as adapter:
            assert await ask(adapter, "first") == "validated answer"
            with pytest.raises(live.LiveCallError, match="budget_exhausted"):
                await ask(adapter, "next")
            with pytest.raises(live.LiveCallError, match="run_stopped"):
                await ask(adapter, "later")

    asyncio.run(run())
    assert len(seen) == 1
    assert read(tmp_path / "run" / "0001-result.json")["status"] == "success"
    assert read(tmp_path / "run" / "0002-blocked.json")["reason"] == reason


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (lambda: httpx.Response(503, text="private provider failure body"), "provider_failure"),
        (
            lambda: httpx.Response(302, headers={"Location": "https://example.test/"}),
            "provider_failure",
        ),
        (lambda: httpx.Response(200, text="private malformed response"), "invalid_response"),
        (lambda: reply(finish_reason="length"), "invalid_response"),
    ],
)
def test_failure_stops_following_requests_and_preserves_partial_progress(tmp_path, failure, expected):
    seen = []

    def respond(request):
        seen.append(request)
        return reply() if len(seen) == 1 else failure()

    async def run():
        async with chat(tmp_path / "run", respond) as adapter:
            assert await ask(adapter, "first") == "validated answer"
            with pytest.raises(live.LiveCallError, match=expected):
                await ask(adapter, "second")
            with pytest.raises(live.LiveCallError, match="run_stopped"):
                await ask(adapter, "third")

    asyncio.run(run())
    assert len(seen) == 2
    assert read(tmp_path / "run" / "0001-result.json")["status"] == "success"
    result_path = tmp_path / "run" / "0002-result.json"
    assert read(result_path)["status"] == expected
    assert "private" not in result_path.read_text()
    assert not (tmp_path / "run" / "0003-started.json").exists()


def test_domain_validation_failure_stops_run_without_leaking_generated_content(tmp_path):
    def reject(_message):
        raise ValueError("private generated invalid references")

    async def run():
        async with chat(tmp_path / "run", lambda _: reply()) as adapter:
            await ask(adapter, validate=reject)

    with pytest.raises(live.LiveCallError, match="invalid_response"):
        asyncio.run(run())
    path = tmp_path / "run" / "0001-result.json"
    assert read(path)["status"] == "invalid_response"
    assert read(path)["input_tokens"] == 12
    assert "private" not in path.read_text()


def test_reported_usage_overrun_stops_and_preserves_what_was_observed(tmp_path):
    response = reply()
    data = response.json()
    data["usage"] = {"prompt_tokens": 11, "completion_tokens": 101, "total_tokens": 112}

    async def run():
        async with chat(tmp_path / "run", lambda _: httpx.Response(200, json=data)) as adapter:
            await ask(adapter)

    with pytest.raises(live.LiveCallError, match="usage_overrun"):
        asyncio.run(run())
    result = read(tmp_path / "run" / "0001-result.json")
    assert result["output_tokens"] == 101
    assert result["status"] == "usage_overrun"


def test_elapsed_deadline_interrupts_transport_and_records_timeout(tmp_path):
    async def delayed(_request):
        await asyncio.sleep(5)
        pytest.fail("request exceeded its remaining time")

    async def run():
        async with chat(tmp_path / "run", delayed, budget=budget(max_elapsed_seconds=1)) as adapter:
            await ask(adapter)

    with pytest.raises(live.LiveCallError, match="timeout"):
        asyncio.run(run())
    assert read(tmp_path / "run" / "0001-result.json")["status"] == "timeout"


def test_existing_receipts_are_preserved_before_loading_key_or_sending(tmp_path):
    receipt_dir = tmp_path / "run"
    receipt_dir.mkdir()
    existing = receipt_dir / "0001-result.json"
    existing.write_text("existing receipt")

    async def run():
        async with chat(receipt_dir, unexpected, key_loader=unexpected):
            pytest.fail("existing run opened")

    with pytest.raises(live.LiveCallError, match="receipt_path_exists"):
        asyncio.run(run())
    assert existing.read_text() == "existing receipt"


def test_proposal_detects_changed_frozen_input(tmp_path):
    source = tmp_path / "public.json"
    source.write_text('{"frozen":true}')
    proposal = {
        "schema": "findings-quality-budget-proposal-v1",
        "provider": "OpenAI",
        "model": "gpt-5.4-mini-2026-03-17",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "pricing_usd_per_million": {"input": "0.75", "output": "4.50"},
        "budget": asdict(budget()),
        "files": {"public.json": hashlib.sha256(source.read_bytes()).hexdigest()},
    }
    path = tmp_path / "budget-proposal.json"
    path.write_text(json.dumps(proposal))
    approval_id, loaded_budget = live.load_proposal(path, repo_root=tmp_path)
    assert approval_id == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded_budget.max_requests == 3
    source.write_text('{"frozen":false}')
    with pytest.raises(live.LiveCallError, match="proposal_input_changed"):
        live.load_proposal(path, repo_root=tmp_path)


def test_unexpected_service_tier_stops_before_estimate_or_validation(tmp_path):
    body = reply().json()
    body["service_tier"] = "priority"

    async def run():
        async with chat(tmp_path / "run", lambda _: httpx.Response(200, json=body)) as adapter:
            await ask(adapter, validate=unexpected)

    with pytest.raises(live.LiveCallError, match="unexpected_service_tier"):
        asyncio.run(run())
    result = read(tmp_path / "run" / "0001-result.json")
    assert result["input_tokens"] == 12
    assert result["observed_estimated_microusd"] is None
    assert result["service_tier"] == "priority"
