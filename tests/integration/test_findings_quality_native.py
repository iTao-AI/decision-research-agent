"""Exercise the coordinator's actual model-facing and file-write boundaries."""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage
import pytest

from scripts.research_findings_consumer import validate_delivery

FIXTURE = Path(__file__).parents[2] / "benchmarks/findings-quality-v1/native.sqlite-foreign-keys.json"
SOURCE_URL = "https://sqlite.org/foreignkeys.html"
PASSAGE = (
    "Foreign key constraints are disabled by default (for backwards compatibility), "
    "so must be enabled separately for each database connection."
)


def candidate_write(*, url=SOURCE_URL, excerpt="enabled separately for each database connection"):
    candidate = {
        "schema_version": "dra.research-findings-candidate.v1",
        "findings": [
            {
                "question_id": "q1",
                "statement": "SQLite's guidance calls for enabling enforcement per connection.",
                "references": [{"source_url": url, "excerpt": excerpt}],
            }
        ],
        "dispositions": [
            {"question_id": "q1", "status": "candidate_findings"},
            {"question_id": "q2", "status": "unresolved", "reason": "Requires the live setting for the application's connection."},
        ],
    }
    return AIMessage(
        content="",
        tool_calls=[{
            "name": "write_file",
            "args": {
                "file_path": "/workspace/research-findings.json",
                "content": json.dumps(candidate, ensure_ascii=False),
            },
            "id": "offline-output-1",
        }],
    )


@pytest.mark.asyncio
async def test_native_arms_share_production_request_except_qualification_instruction():
    from scripts.findings_quality_native import QUALIFICATION_INSTRUCTION, load_native_fixture, run_native_arm

    requests = []

    async def generate(request):
        requests.append(request)
        return candidate_write()

    fixture = load_native_fixture(FIXTURE)
    a = await run_native_arm(fixture=fixture, arm="A", generate=generate)
    b = await run_native_arm(fixture=fixture, arm="B", generate=generate)

    assert len(requests) == 2
    assert requests[0].tools == requests[1].tools
    by_name = {tool["function"]["name"]: tool["function"] for tool in requests[0].tools}
    assert set(by_name["write_file"]["parameters"]["properties"]) == {"file_path", "content"}
    assert "task" in by_name
    assert requests[0].messages[1:] == requests[1].messages[1:]
    baseline, variant = requests[0].messages[0], requests[1].messages[0]
    assert baseline["role"] == variant["role"] == "system"
    assert "Coordinate bounded research using only the named researchers" in baseline["content"]
    assert variant["content"] == baseline["content"] + "\n\n" + QUALIFICATION_INSTRUCTION
    assert any("/workspace/research-findings.json" in item["content"] for item in requests[0].messages if item["role"] == "user")
    for result in (a, b):
        receipt = result.receipt
        assert receipt["outcome"] == "delivered"
        assert receipt["source_tool_calls"] == 1
        observed = receipt["visible_source"]
        assert observed["passage"] == PASSAGE
        message = requests[0].messages[observed["message_index"]]
        assert message["role"] == "tool"
        start = observed["start"]
        assert message["content"][start : start + len(PASSAGE)] == PASSAGE
        assert receipt["model_request_id"] not in {receipt["run_id"], receipt["segment_id"]}
        assert receipt["provider_response_id"] is None
        checked = validate_delivery(result.delivery, receipt["run_id"])
        assert checked["checks"]["same_run_evidence_binding"]
        assert checked["references"][0]["verification_status"] == "unverified"
        assert result.candidate_content == candidate_write().tool_calls[0]["args"]["content"]
    assert a.receipt["run_id"] != b.receipt["run_id"]
    assert a.receipt["tools_sha256"] == b.receipt["tools_sha256"]
    assert a.receipt["baseline_messages_sha256"] == b.receipt["baseline_messages_sha256"]
    assert a.receipt["request_sha256"] != b.receipt["request_sha256"]
    assert a.delivery["evidence"][0]["evidence_id"] != b.delivery["evidence"][0]["evidence_id"]


@pytest.mark.asyncio
async def test_failed_binding_retains_candidate_without_using_another_fixture(tmp_path):
    from scripts.findings_quality_native import load_native_fixture, run_native_arm

    first = load_native_fixture(FIXTURE)
    async def generate(_):
        return candidate_write()

    delivered = await run_native_arm(fixture=first, arm="A", generate=generate)
    assert delivered.delivery is not None
    second_data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    second_data["fixture_id"] = "different-public-fixture"
    second_data["frozen_search_result"]["results"][0]["content"] = "A wholly distinct source observation."
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(second_data), encoding="utf-8")
    blocked = await run_native_arm(fixture=load_native_fixture(second_path), arm="B", generate=generate)
    assert blocked.candidate_content == delivered.candidate_content
    assert blocked.delivery is None
    assert blocked.receipt["outcome"] == "blocked"
    assert blocked.receipt["binding_issues"] == ["excerpt_not_found"]
    assert blocked.receipt["visible_source"]["passage"] == "A wholly distinct source observation."


@pytest.mark.asyncio
async def test_skipped_native_write_has_no_candidate_or_implied_provider_observation():
    from scripts.findings_quality_native import load_native_fixture, run_native_arm

    async def generate(_):
        return AIMessage(content="No candidate from this response.")

    result = await run_native_arm(fixture=load_native_fixture(FIXTURE), arm="A", generate=generate)
    assert result.candidate_content is None
    assert result.delivery is None
    assert result.receipt["binding_issues"] == ["candidate_missing"]
    assert result.receipt["native_generation_calls"] == 1
    assert result.receipt["provider_response_id"] is None


@pytest.mark.asyncio
async def test_arm_a_request_matches_independent_normal_harness_execution(tmp_path, monkeypatch):
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import ToolMessage, convert_to_openai_messages
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from agent.deepagents_harness import build_generic_harness
    from api.research_execution_service import ResearchExecutionService
    from scripts.findings_quality_native import load_native_fixture, run_native_arm
    import tools.tavily_tools as tavily

    observed = {}
    fixture = load_native_fixture(FIXTURE)

    class OrdinaryModel(BaseChatModel):
        bound_tools: tuple[dict, ...] = ()
        profile: dict | None = {"max_input_tokens": 32768}

        @property
        def _llm_type(self):
            return "normal-coordinator-test-model"

        def bind_tools(self, tools, **kwargs):
            converted = tuple(convert_to_openai_tool(tool) for tool in tools)
            return self.model_copy(update={"bound_tools": converted})

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            results = {message.name: message.content for message in messages if isinstance(message, ToolMessage)}
            names = {tool["function"]["name"] for tool in self.bound_tools}
            if "internet_search" in names and not results:
                reply = AIMessage(content="", tool_calls=[{
                    "name": "internet_search", "id": "fql-public-search",
                    "args": {"query": fixture.search_query},
                }])
            elif "internet_search" in names:
                observed["search_tools"] = self.bound_tools
                reply = AIMessage(content=results["internet_search"])
            elif "task" not in results:
                reply = AIMessage(content="", tool_calls=[{
                    "name": "task", "id": "fql-public-task",
                    "args": {"description": fixture.research_task, "subagent_type": "network_search"},
                }])
            elif "write_file" in results:
                reply = AIMessage(content="Generation completed.")
            else:
                observed["normal_messages"] = convert_to_openai_messages(messages)
                observed["normal_tools"] = list(self.bound_tools)
                reply = candidate_write()
            return ChatResult(generations=[ChatGeneration(message=reply)])

    def frozen_provider(query, **kwargs):
        observed["normal_search_query"] = query
        return fixture.search_result

    monkeypatch.setattr(tavily, "_internet_search_impl", frozen_provider)
    ordinary = await ResearchExecutionService(
        harness=build_generic_harness(model=OrdinaryModel()), project_root=tmp_path,
    ).execute(
        fixture.query, "normal-execution",
        profile_id="generic-evidence-report", scope=json.loads(fixture.scope_json),
    )

    async def candidate(request):
        observed["arm_a"] = request
        return candidate_write()

    evaluated = await run_native_arm(fixture=fixture, arm="A", generate=candidate)
    assert observed["normal_search_query"] == fixture.search_query
    assert observed["search_tools"] == (convert_to_openai_tool(tavily.internet_search),)
    assert observed["arm_a"].messages == observed["normal_messages"]
    assert observed["arm_a"].tools == observed["normal_tools"]
    assert ordinary.evidence_entries[0].snippet == PASSAGE
    assert evaluated.candidate_content == ordinary.findings_candidate.content


@pytest.mark.asyncio
@pytest.mark.parametrize(("arm", "tool_name"), [("A", "write_file"), ("B", "write_file"), ("A", "task")])
async def test_native_chat_adapter_can_only_execute_candidate_write(arm, tool_name, tmp_path):
    import httpx

    from scripts.findings_quality_native import generation_with_chat, load_native_fixture, run_native_arm
    from scripts.findings_quality_transport import BoundedChat, ChatBudget, LiveCallError, MODEL

    receipt_dir = tmp_path / "transport"
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        args = candidate_write().tool_calls[0]["args"] if tool_name == "write_file" else {
            "description": "This must not start another research task.", "subagent_type": "network_search",
        }
        return httpx.Response(200, json={
            "id": "chatcmpl-frozen-proof", "object": "chat.completion", "model": MODEL,
            "choices": [{
                "index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [{
                    "type": "function", "id": "call-scripted-output",
                    "function": {"name": tool_name, "arguments": json.dumps(args)},
                }]},
            }],
            "usage": {"prompt_tokens": 2048, "completion_tokens": 281},
        })

    kwargs = {
        "fixture": load_native_fixture(FIXTURE),
        "arm": arm,
    }
    async with BoundedChat(
        opt_in=True, approval_id="a" * 64, proposal_sha256="a" * 64,
        budget=ChatBudget(
            max_requests=1, max_input_tokens=40_000, max_input_tokens_per_request=40_000,
            max_output_tokens=1_000, max_output_tokens_per_request=1_000,
            max_elapsed_seconds=15, max_estimated_microusd=40_000,
        ),
        receipt_dir=receipt_dir, transport=httpx.MockTransport(respond),
        key_loader=lambda: "scripted-key",
    ) as chat:
        if tool_name == "write_file":
            result = await run_native_arm(**kwargs, generate=generation_with_chat(chat))
            assert result.delivery["report"]["findings"][0]["references"][0]["snippet"] == PASSAGE
            receipt = result.receipt
        else:
            with pytest.raises(LiveCallError, match="invalid_response") as caught:
                await run_native_arm(**kwargs, generate=generation_with_chat(chat))
            receipt = caught.value.native_receipt

    assert len(seen) == 1
    assert {tool["function"]["name"] for tool in seen[0]["tools"]} >= {"task", "write_file"}
    assert receipt["source_tool_call_id"] == "fql-public-search"
    assert receipt["visible_source"]["passage"] == PASSAGE
    transport_record = json.loads((receipt_dir / "0001-result.json").read_text())
    assert transport_record["request_id"] == receipt["model_request_id"]
    assert transport_record["request_id"].startswith(f"generation.{arm}.")
    assert transport_record["reserved_input_tokens"] < 40_000
    assert transport_record["execution_mode"] == "scripted"
    assert transport_record["status"] == ("success" if tool_name == "write_file" else "invalid_response")
    assert transport_record["provider_response_id"] == "chatcmpl-frozen-proof"
    assert transport_record["input_tokens"] == 2048
    assert transport_record["output_tokens"] == 281


@pytest.mark.asyncio
async def test_native_locates_json_escaped_passage_and_binds_original_excerpt(tmp_path):
    from scripts.findings_quality_native import load_native_fixture, run_native_arm

    quoted = 'A "SQLite" note for C:\\examples says to enable it separately for each database connection.'
    recipe = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recipe["fixture_id"] = "sqlite-escaped-source"
    recipe["frozen_search_result"]["results"][0]["content"] = quoted
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(recipe), encoding="utf-8")
    requests = []

    async def generate(request):
        requests.append(request)
        return candidate_write(excerpt=quoted)

    result = await run_native_arm(fixture=load_native_fixture(path), arm="A", generate=generate)
    assert result.receipt["outcome"] == "delivered"
    source = result.receipt["visible_source"]
    wire = requests[0].messages[source["message_index"]]["content"]
    encoded_span = wire[source["start"]:source["end"]]
    assert encoded_span != quoted
    assert json.loads('"' + encoded_span + '"') == source["passage"] == quoted
    assert result.delivery["report"]["findings"][0]["references"][0]["excerpt"] == quoted
