"""Provider-injectable comparison at the ordinary coordinator model call.

Only the final candidate-producing turn is delegated to the injected generator.
Public retrieval bytes and the other turns are fixed locally. The coordinator
graph, workspace writer, stream capture, binder and reader are the application's.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage, convert_to_openai_messages
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langsmith import tracing_context

from agent.deepagents_harness import build_generic_harness
from agent.harness_contracts import FINDINGS_CANDIDATE_PATH, MAX_FINDINGS_CANDIDATE_BYTES
from agent.research import EvidenceEntry
from agent.research_findings_contracts import ResearchFindingsScope
from agent.run_result import OutcomeBox
from agent.source_url_policy import is_publishable_source_url
from api.publication_repository import evidence_verification_enabled, init_publication_schema
from api.research_execution_service import ResearchExecutionService
from api.research_findings import RESEARCH_FINDINGS_PROFILE_ID, build_research_findings_artifacts
from api.research_findings_service import resolve_run_findings
from api.run_repository import create_run, finalize_run_transaction, get_run
from scripts.findings_quality_transport import BoundedChat, LiveCallError
from scripts.research_findings_consumer import strict_json, validate_delivery

QUALIFICATION_INSTRUCTION = (
    "When stating a finding, preserve the object, version and applicable conditions "
    "shown in the quoted evidence. If a necessary qualification cannot be established "
    "from the cited material, identify the missing evidence or condition."
)
_RUN_PACKAGES = ("deepagents", "langchain", "langchain-core", "langgraph", "pydantic")
_MAX_FIXTURE_BYTES = 16 * 1024
_TASK_CALL_ID = "fql-public-task"
_SEARCH_CALL_ID = "fql-public-search"


@dataclass(frozen=True)
class NativeFixture:
    fixture_id: str
    sha256: str
    query: str
    scope_json: str
    research_task: str
    search_query: str
    search_result: str
    source_url: str
    passage: str


@dataclass(frozen=True)
class NativeGenerationRequest:
    request_id: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]


@dataclass(frozen=True)
class NativeArmResult:
    receipt: dict[str, Any]
    candidate_content: str | None
    delivery: dict[str, Any] | None


class NativeLiveCallError(LiveCallError):
    """A stopped paid call with its public, already observed native context."""

    def __init__(self, code: str, receipt: dict[str, Any]) -> None:
        super().__init__(code)
        self.native_receipt = receipt


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_native_fixture(path: Path) -> NativeFixture:
    with path.open("rb") as stream:
        content = stream.read(_MAX_FIXTURE_BYTES + 1)
    if len(content) > _MAX_FIXTURE_BYTES:
        raise ValueError("native_fixture_too_large")

    def bounded_text(value: object, maximum: int) -> bool:
        return type(value) is str and 0 < len(value.strip()) <= maximum and value == value.strip()

    try:
        raw = strict_json(content.decode("utf-8"))
        result = raw["frozen_search_result"]
        (source,) = result["results"]
        scope = ResearchFindingsScope.model_validate(raw["scope"])
        provenance = raw["provenance"]
        if (
            set(raw) != {"schema_version", "fixture_id", "provenance", "query", "scope", "research_task", "search_query", "frozen_search_result"}
            or raw["schema_version"] != "dra.findings-quality-native-fixture.v1"
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", raw["fixture_id"])
            or not all(bounded_text(raw[key], 500) for key in ("query", "research_task", "search_query"))
            or set(result) != {"results"}
            or set(source) != {"url", "content"}
            or not is_publishable_source_url(source["url"])
            or not bounded_text(source["content"], 1000)
            or source["content"] != " ".join(source["content"].split())
            or set(provenance) != {"kind", "source_url", "locator", "checked_on"}
            or provenance["kind"] != "public_documentation_synthetic_history"
            or provenance["source_url"] != source["url"]
            or not bounded_text(provenance["locator"], 500)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", provenance["checked_on"])
        ):
            raise ValueError("invalid frozen fixture")
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError("native_fixture_invalid") from exc
    return NativeFixture(
        fixture_id=raw["fixture_id"],
        sha256=_hash(content),
        query=raw["query"],
        scope_json=_canonical(scope.model_dump(mode="json")),
        research_task=raw["research_task"],
        search_query=raw["search_query"],
        search_result=_canonical(result),
        source_url=source["url"],
        passage=source["content"],
    )


def _tool_result(message: AIMessage) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=message)])


def _call_tool(name: str, call_id: str, args: dict[str, Any]) -> ChatResult:
    return _tool_result(AIMessage(
        content="",
        tool_calls=[{"name": name, "id": call_id, "args": args}],
    ))


def _valid_candidate_reply(message: AIMessage) -> None:
    calls = message.tool_calls
    if message.invalid_tool_calls or len(calls) > 1:
        raise ValueError("native_candidate_tool_invalid")
    if not calls:
        return
    call = calls[0]
    args = call["args"]
    content = args.get("content")
    if (
        call["name"] != "write_file"
        or not isinstance(call["id"], str)
        or not call["id"]
        or set(args) != {"file_path", "content"}
        or args["file_path"] != FINDINGS_CANDIDATE_PATH.as_posix()
        or type(content) is not str
        or len(content.encode("utf-8")) > MAX_FINDINGS_CANDIDATE_BYTES
    ):
        raise ValueError("native_candidate_tool_invalid")


def _qualification_hash(arm: str) -> str | None:
    return _hash(QUALIFICATION_INSTRUCTION.encode("utf-8")) if arm == "B" else None


def native_request_evidence(
    fixture: NativeFixture, arm: Literal["A", "B"], messages: list[dict[str, Any]], tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive native receipt fields from the exact candidate-turn envelope."""
    system = messages[0]
    if system["role"] != "system" or not isinstance(system["content"], str):
        raise ValueError("native_system_format_changed")
    suffix = "\n\n" + QUALIFICATION_INSTRUCTION
    if system["content"].endswith(suffix) != (arm == "B"):
        raise ValueError("native_qualification_instruction_mismatch")
    baseline = ([{**system, "content": system["content"][:-len(suffix)]}, *messages[1:]]
                if arm == "B" else messages)
    sources = [(index, item["content"]) for index, item in enumerate(messages)
               if item.get("tool_call_id") == _TASK_CALL_ID and item["role"] == "tool"]
    encoded_passage = _canonical(fixture.passage)[1:-1]
    if len(sources) != 1:
        raise ValueError("native_frozen_source_not_visible")
    source_index, source_text = sources[0]
    if (not isinstance(source_text, str) or source_text.count(encoded_passage) != 1
            or fixture.search_result not in source_text):
        raise ValueError("native_frozen_source_not_visible")
    source_start = source_text.index(encoded_passage)
    return {
        "qualification_instruction_sha256": _qualification_hash(arm),
        "baseline_messages_sha256": _hash(_canonical(baseline).encode("utf-8")),
        "request_sha256": _hash(_canonical({"messages": messages, "tools": tools}).encode("utf-8")),
        "tools_sha256": _hash(_canonical(tools).encode("utf-8")),
        "visible_source": {
            "source_url": fixture.source_url, "passage": fixture.passage,
            "passage_sha256": _hash(fixture.passage.encode("utf-8")), "message_index": source_index,
            "start": source_start, "end": source_start + len(encoded_passage), "tool_call_id": _TASK_CALL_ID,
        },
    }


def native_request_matches_fixture(fixture: NativeFixture, messages: list[dict[str, Any]]) -> bool:
    """Verify the supplied query and accepted questions in the coordinator input."""
    users = [item["content"] for item in messages if item["role"] == "user"]
    if len(users) != 1:
        return False
    envelope = strict_json(users[0].split("\n", 2)[1])
    calls = [call["function"] for item in messages if item["role"] == "assistant"
             for call in item.get("tool_calls") or [] if call["id"] == _TASK_CALL_ID]
    return (envelope["profile_id"] == RESEARCH_FINDINGS_PROFILE_ID and envelope["query"] == fixture.query
            and _canonical(envelope["scope"]) == fixture.scope_json
            and len(calls) == 1 and calls[0]["name"] == "task"
            and strict_json(calls[0]["arguments"]) == {
                "description": fixture.research_task, "subagent_type": "network_search",
            })


class _FrozenHistoryModel(BaseChatModel):
    fixture: NativeFixture
    arm: Literal["A", "B"]
    generate_candidate: Callable[[NativeGenerationRequest], Awaitable[AIMessage]]
    observations: dict[str, Any]
    bound_tools: tuple[dict[str, Any], ...] = ()
    profile: dict[str, Any] | None = {"max_input_tokens": 32768}
    cache: bool = False

    @property
    def _llm_type(self) -> str:
        return "findings-quality-fixture"

    def bind_tools(self, tools: Sequence, **kwargs):
        return self.model_copy(update={"bound_tools": tuple(convert_to_openai_tool(tool) for tool in tools)})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("native_quality_requires_async_execution")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        names = {tool["function"]["name"] for tool in self.bound_tools}
        history = {item.tool_call_id: item for item in messages if isinstance(item, ToolMessage)}
        if "internet_search" in names:
            source = history.get(_SEARCH_CALL_ID)
            if source is None:
                return _call_tool("internet_search", _SEARCH_CALL_ID, {"query": self.fixture.search_query})
            if source.status != "success" or source.content != self.fixture.search_result:
                raise ValueError("native_frozen_source_not_observed")
            self.observations["source_tool_call_id"] = source.tool_call_id
            return _tool_result(AIMessage(content=source.content))

        if not {"task", "write_file"} <= names:
            raise ValueError("native_coordinator_tool_contract_unavailable")
        if _TASK_CALL_ID not in history:
            return _call_tool("task", _TASK_CALL_ID, {
                "description": self.fixture.research_task,
                "subagent_type": "network_search",
            })
        if self.observations["native_generation_calls"]:
            return _tool_result(AIMessage(content="Frozen generation turn complete."))

        wire = convert_to_openai_messages(messages)
        if self.arm == "B":
            if wire[0]["role"] != "system" or not isinstance(wire[0]["content"], str):
                raise ValueError("native_system_format_changed")
            wire[0]["content"] += "\n\n" + QUALIFICATION_INSTRUCTION

        request_id = f"generation.{self.arm}.{uuid4().hex}"
        tools = list(self.bound_tools)
        self.observations.update(
            native_generation_calls=1, model_request_id=request_id,
            **native_request_evidence(self.fixture, self.arm, wire, tools),
        )
        candidate = await self.generate_candidate(NativeGenerationRequest(request_id, wire, tools))
        _valid_candidate_reply(candidate)
        response_id = candidate.response_metadata.get("provider_response_id")
        if isinstance(response_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", response_id):
            self.observations["provider_response_id"] = response_id
        return _tool_result(candidate)


async def run_native_arm(
    *,
    fixture: NativeFixture,
    arm: Literal["A", "B"],
    generate: Callable[[NativeGenerationRequest], Awaitable[AIMessage]],
    skills_root: Path | None = None,
) -> NativeArmResult:
    """Run a single frozen arm and independently read the same-run delivery."""
    if arm not in {"A", "B"}:
        raise ValueError("native_arm_invalid")
    scope = ResearchFindingsScope.model_validate_json(fixture.scope_json)
    scope_data = scope.model_dump(mode="json")
    receipt: dict[str, Any] = {
        "schema_version": "dra.findings-quality-native-receipt.v1",
        "boundary": "production_coordinator_candidate_turn",
        "fixture_id": fixture.fixture_id,
        "fixture_sha256": fixture.sha256,
        "arm": arm,
        "qualification_instruction_sha256": _qualification_hash(arm),
        "versions": {name: version(name) for name in _RUN_PACKAGES},
        "source_origin": "frozen_public_tool_result",
        "source_tool_calls": 0,
        "source_tool_call_id": None,
        "native_generation_calls": 0,
        "model_request_id": None,
        "provider_response_id": None,
        "baseline_messages_sha256": None,
        "request_sha256": None,
        "tools_sha256": None,
        "visible_source": None,
        "delivery_sha256": None,
    }
    model = _FrozenHistoryModel(fixture=fixture, arm=arm, generate_candidate=generate, observations=receipt)
    receipt = model.observations

    def replay_search(query: str, **kwargs: Any) -> str:
        if query != fixture.search_query or receipt["source_tool_calls"]:
            raise ValueError("native_frozen_source_query_invalid")
        receipt["source_tool_calls"] = 1
        return fixture.search_result

    with TemporaryDirectory(prefix="dra-findings-quality-") as scratch, tracing_context(enabled=False):
        root = Path(scratch)
        db_path = str(root / "evaluation.sqlite3")
        if evidence_verification_enabled():
            init_publication_schema(db_path)
        identifiers = create_run(
            db_path=db_path, thread_id=f"eval_{uuid4().hex}", query=fixture.query,
            profile_id=RESEARCH_FINDINGS_PROFILE_ID, scope=scope_data,
        )
        run_id = identifiers["run_id"]
        receipt.update(run_id=run_id, segment_id=identifiers["segment_id"])
        harness = build_generic_harness(model=model, network_search_override=replay_search, skills_root=skills_root)
        outcome_box = OutcomeBox()
        try:
            outcome = await ResearchExecutionService(harness=harness, project_root=root).execute(
                fixture.query, **identifiers, profile_id=RESEARCH_FINDINGS_PROFILE_ID,
                scope=scope_data, outcome_box=outcome_box,
            )
        except LiveCallError as exc:
            outcome = outcome_box.latest()
            receipt.update(
                outcome=exc.code,
                binding_issues=None,
                candidate_sha256=None,
                frozen_evidence_fingerprints=(
                    [entry.evidence_fingerprint for entry in outcome.evidence_entries]
                    if outcome is not None else None
                ),
            )
            raise NativeLiveCallError(exc.code, receipt) from None
        candidate = outcome.findings_candidate.content if outcome.findings_candidate else None
        built = build_research_findings_artifacts(
            run_id=run_id, scope=scope, candidate_content=candidate,
            evidence_entries=outcome.evidence_entries, capture_issue=outcome.findings_capture_issue,
        )
        receipt["binding_issues"] = list(built.diagnostics.issue_codes)
        receipt["candidate_sha256"] = _hash(candidate.encode("utf-8")) if candidate is not None else None
        receipt["frozen_evidence_fingerprints"] = [
            entry.evidence_fingerprint for entry in outcome.evidence_entries
        ]
        receipt["outcome"] = "delivered" if built.delivery_status == "ready" else "blocked"
        delivery = None
        if built.delivery_status == "ready":
            finalized = finalize_run_transaction(
                db_path=db_path, run_id=run_id, segment_id=identifiers["segment_id"],
                expected_state_version=0, allowed_previous_statuses={"pending"},
                execution_status="completed", delivery_status=built.delivery_status,
                evidence_entries=built.evidence_entries, artifacts=built.artifacts,
            )
            if not finalized:
                raise RuntimeError("native_evaluation_finalization_failed")
            resolved = resolve_run_findings(run_id=run_id, db_path=db_path)
            stored = get_run(run_id=run_id, db_path=db_path)
            delivery = {
                "run_id": run_id,
                "execution_status": resolved.execution_status,
                "delivery_status": resolved.delivery_status,
                "artifact": resolved.artifact,
                "report": resolved.report.model_dump(mode="json"),
                "evidence": stored["evidence"],
                "review_status": stored["review_status"],
                "review_decision": None,
            }
            validated = validate_delivery(delivery, run_id)
            receipt["delivery_sha256"] = validated["artifact"]["content_hash"]
    return NativeArmResult(receipt, candidate, delivery)



def rebind_captured_report(fixture: NativeFixture, *, candidate: str, delivery: dict, receipt: dict) -> bool:
    """Require the canonical report from that candidate and the fixture's one frozen passage."""
    run_id = receipt["run_id"]
    entry = EvidenceEntry(thread_id="findings-quality-replay", query_text=fixture.query, subagent_name="network_search",
                          tool_name="internet_search", source_url=fixture.source_url, snippet=fixture.passage)
    fingerprints = [entry.evidence_fingerprint]
    if (receipt["frozen_evidence_fingerprints"] != fingerprints
            or [row["evidence_fingerprint"] for row in delivery["evidence"]] != fingerprints):
        return False
    rebound = build_research_findings_artifacts(
        run_id=run_id, scope=ResearchFindingsScope.model_validate_json(fixture.scope_json),
        candidate_content=candidate, evidence_entries=[entry],
    )
    return rebound.delivery_status == "ready" and rebound.artifacts[0]["content"] == delivery["artifact"]["content"]

def _decode_candidate(message: dict[str, Any]) -> AIMessage:
    calls = [
        {
            "name": call["function"]["name"],
            "id": call["id"],
            "args": strict_json(call["function"]["arguments"]),
        }
        for call in message.get("tool_calls") or []
    ]
    candidate = AIMessage(content=message.get("content") or "", tool_calls=calls)
    _valid_candidate_reply(candidate)
    return candidate


def generation_with_chat(chat: BoundedChat) -> Callable[[NativeGenerationRequest], Awaitable[AIMessage]]:
    """Use the approval and budgets of the caller's explicitly scoped adapter."""
    async def generate(request: NativeGenerationRequest) -> AIMessage:
        return await chat.complete(
            kind="generation", request_id=request.request_id,
            messages=request.messages, tools=request.tools, validate=_decode_candidate,
        )

    return generate
