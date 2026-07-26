import json
from pathlib import PurePosixPath
import traceback
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent.harness_contracts import ReportCandidate
from agent.research import EvidenceEntry
from agent.run_result import ExecutionOutcome
from api.run_result_service import build_generic_result_artifact


def _outcome(
    *,
    report="# Report\n\nSupported finding.",
    evidence=None,
):
    return ExecutionOutcome(
        thread_id="thread-1",
        query="Research question",
        session_dir=PurePosixPath("/workspace"),
        profile_id="generic-strict-citation",
        run_id="run-1",
        segment_id="segment-1",
        report_candidate=ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content=report,
        ),
        evidence_entries=list(evidence or []),
    )


def _evidence(url="https://example.com/source", *, snippet="Source context"):
    return EvidenceEntry(
        thread_id="thread-1",
        query_text="Research question",
        subagent_name="network_search",
        tool_name="internet_search",
        source_url=url,
        snippet=snippet,
    )


class ScriptedChatModel(BaseChatModel):
    response: Any = AIMessage(
        content='{"placements":[{"target_id":"t001","source_id":"s001"}]}'
    )
    error_text: str | None = None
    call_count: int = 0
    captured_input: Any = None
    captured_config: Any = None

    @property
    def _llm_type(self) -> str:
        return "scripted-strict-citation"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self.response)])

    async def ainvoke(self, input, config=None, **kwargs):
        del kwargs
        self.call_count += 1
        self.captured_input = input
        self.captured_config = config
        if self.error_text:
            raise RuntimeError(self.error_text)
        return self.response


def test_target_scanner_is_deterministic_and_conservative():
    from api.strict_citation_finalization import _extract_targets

    report = (
        "# Heading\n\n"
        "Plain paragraph.\n\n"
        "- List prose\n"
        "> Quote prose\n\n"
        "```python\nnot eligible\n```\n\n"
        "| table | row |\n\n"
        "Secret password=value\n\n"
        "Final paragraph."
    )

    targets = _extract_targets(report)

    assert [target.target_id for target in targets] == [
        "t001",
        "t002",
        "t003",
        "t004",
    ]
    assert [target.excerpt for target in targets] == [
        "Plain paragraph.",
        "- List prose",
        "> Quote prose",
        "Final paragraph.",
    ]
    for target in targets:
        assert report[target.start : target.end] == target.excerpt
        assert len(target.basis_sha256) == 64


def test_target_scanner_excludes_ambiguous_blocks_and_bounds_utf8():
    from api.strict_citation_finalization import _extract_targets

    report = (
        "Setext heading\n---\n\n"
        "[ref]: https://example.com\n    continuation\n\n"
        "<div>\nhtml\n</div>\n\n"
        "> ```\n> fenced\n> ```\n\n"
        "pipe \\| remains ambiguous\n\n"
        + ("界" * 300)
    )

    targets = _extract_targets(report)

    assert len(targets) == 1
    assert len(targets[0].excerpt.encode("utf-8")) <= 512


def test_source_projection_deduplicates_and_omits_sensitive_context():
    from api.strict_citation_finalization import _project_sources

    outcome = _outcome(
        evidence=[
            _evidence("https://example.com/a(b", snippet="password=hidden"),
            _evidence("https://example.com/a(b", snippet="duplicate"),
            _evidence("http://example.com/not-public"),
            _evidence("https://example.com/unsafe>"),
        ]
    )

    sources = _project_sources(outcome)

    assert [(source.source_id, source.source_url) for source in sources] == [
        ("s001", "https://example.com/a(b")
    ]
    assert sources[0].snippet == "[context omitted]"


def test_prepare_builds_bounded_canonical_untrusted_packet():
    from api.strict_citation_finalization import (
        PreparedStrictCitation,
        prepare_strict_citation,
    )

    outcome = _outcome(evidence=[_evidence()])
    prepared = prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )

    assert isinstance(prepared, PreparedStrictCitation)
    assert [type(message).__name__ for message in prepared.messages] == [
        "SystemMessage",
        "HumanMessage",
    ]
    packet_text = prepared.messages[1].content
    assert packet_text.startswith("BEGIN_UNTRUSTED_PACKET\n")
    assert packet_text.endswith("\nEND_UNTRUSTED_PACKET")
    payload = json.loads(packet_text.splitlines()[1])
    assert set(payload) == {"instruction", "schema", "sources", "targets"}
    assert payload["sources"][0]["source_id"] == "s001"
    assert len(packet_text.encode("utf-8")) <= 512 * 1024


@pytest.mark.parametrize(
    ("report", "evidence", "code"),
    [
        ("# Heading", [_evidence()], "strict_citation_target_unavailable"),
        ("Supported finding.", [], "strict_citation_source_unavailable"),
    ],
)
def test_prepare_fails_closed_before_invocation(report, evidence, code):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        prepare_strict_citation,
    )

    outcome = _outcome(report=report, evidence=evidence)
    with pytest.raises(StrictCitationFinalizationError, match=code):
        prepare_strict_citation(
            outcome=outcome,
            initial_artifact=build_generic_result_artifact(outcome),
        )


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        '{"placements":[]}',
        '{"placements":[{"target_id":"unknown","source_id":"s001"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001","url":"x"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001"},{"target_id":"t001","source_id":"s001"}]}',
    ],
)
def test_parser_rejects_every_non_exact_response(content):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        _parse_placements,
    )

    prepared = prepare_for_call()
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_response_invalid",
    ):
        _parse_placements(content, prepared.targets, prepared.sources)


def prepare_for_call(report="Supported first.\n\nSupported second."):
    from api.strict_citation_finalization import prepare_strict_citation

    outcome = _outcome(report=report, evidence=[_evidence()])
    return prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )


def test_prepare_zero_call_when_initial_artifact_is_already_cited():
    from api.strict_citation_finalization import (
        StrictCitationResult,
        prepare_strict_citation,
    )

    outcome = _outcome(
        report="Supported https://example.com/source.",
        evidence=[_evidence()],
    )
    model = ScriptedChatModel()

    result = prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )

    assert isinstance(result, StrictCitationResult)
    assert result.evidence_entries[0].citation_status == "cited"
    assert model.call_count == 0


@pytest.mark.asyncio
async def test_invoke_calls_once_and_renders_exact_url_in_target_order():
    from api.strict_citation_finalization import invoke_prepared_strict_citation

    prepared = prepare_for_call()
    model = ScriptedChatModel(
        response=AIMessage(
            content=json.dumps(
                {
                    "placements": [
                        {"target_id": "t002", "source_id": "s001"},
                        {"target_id": "t001", "source_id": "s001"},
                    ]
                }
            )
        )
    )

    result = await invoke_prepared_strict_citation(
        prepared=prepared,
        chat_model=model,
    )

    assert model.call_count == 1
    assert result.artifact["content"] == (
        "Supported first. [Source](<https://example.com/source>)\n\n"
        "Supported second. [Source](<https://example.com/source>)"
    )
    assert result.evidence_entries[0].citation_status == "cited"
    assert model.captured_input == prepared.messages
    assert model.captured_config == prepared.config


@pytest.mark.asyncio
async def test_invoke_maps_provider_and_parser_errors_without_context():
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        invoke_prepared_strict_citation,
    )

    prepared = prepare_for_call()
    provider_model = ScriptedChatModel(error_text="provider-secret-detail")
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_model_failed",
    ):
        await invoke_prepared_strict_citation(
            prepared=prepared,
            chat_model=provider_model,
        )
    assert "provider-secret-detail" not in traceback.format_exc()
    assert provider_model.call_count == 1

    parser_model = ScriptedChatModel(response=AIMessage(content="malformed"))
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_response_invalid",
    ):
        await invoke_prepared_strict_citation(
            prepared=prepared,
            chat_model=parser_model,
        )
    assert parser_model.call_count == 1
