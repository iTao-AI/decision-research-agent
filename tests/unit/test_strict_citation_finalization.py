import json
from dataclasses import replace
import hashlib
from pathlib import PurePosixPath
import traceback
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
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


def test_target_scanner_caps_ids_and_preserves_exact_offsets():
    from api.strict_citation_finalization import _extract_targets

    report = "\n\n".join(
        f"Paragraph {index}." for index in range(1, 131)
    )

    targets = _extract_targets(report)

    assert len(targets) == 128
    assert targets[0].target_id == "t001"
    assert targets[-1].target_id == "t128"
    for index, target in enumerate(targets, start=1):
        exact = f"Paragraph {index}."
        assert report[target.start : target.end] == exact
        assert target.excerpt == exact
        assert target.basis_sha256 == hashlib.sha256(
            exact.encode("utf-8")
        ).hexdigest()


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (
            "```python\ninside\n````   \nVisible prose.",
            ["Visible prose."],
        ),
        (
            "~~~python\ninside\n~~~~\t\nVisible prose.",
            ["Visible prose."],
        ),
        (
            "```python\ninside\n~~~\nstill inside\n```\nVisible prose.",
            ["Visible prose."],
        ),
        (
            "```python\ninside\n```not-a-close\nstill inside\n```\nVisible prose.",
            ["Visible prose."],
        ),
        (
            "> ```python\n> inside\n> ```\n> Visible quote prose.",
            ["> Visible quote prose."],
        ),
        (
            "- ~~~python\n  inside\n  ~~~\n- Visible list prose.",
            ["- Visible list prose."],
        ),
        (
            "> - ```python\n>   inside\n>   ```\n> - Visible nested prose.",
            ["> - Visible nested prose."],
        ),
    ],
)
def test_target_scanner_handles_fence_matrix(report, expected):
    from api.strict_citation_finalization import _extract_targets

    assert [target.excerpt for target in _extract_targets(report)] == expected


@pytest.mark.parametrize(
    "prefix",
    [
        "> " * 9,
        ("> " * 5) + ("- " * 5),
    ],
)
def test_target_scanner_excludes_fences_beyond_legacy_container_depth(prefix):
    from api.strict_citation_finalization import _extract_targets

    report = (
        f"{prefix}```python\n"
        f"{prefix}inside code\n"
        f"{prefix}```\n"
        "Safe prose."
    )

    targets = _extract_targets(report)

    assert [target.excerpt for target in targets] == ["Safe prose."]
    assert report[targets[0].start : targets[0].end] == "Safe prose."


@pytest.mark.parametrize(
    "report",
    [
        "```python\ninside\n```not-a-close\ncode link target\n",
        "~~~python\ninside\n```\ncode link target\n",
        "> ```python\n> inside\n> code link target\n",
        "- ~~~python\n  inside\n  code link target\n",
    ],
)
def test_target_scanner_unterminated_or_mismatched_fence_fails_closed(report):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        _extract_targets,
    )

    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_target_unavailable",
    ):
        _extract_targets(report)


@pytest.mark.parametrize(
    "report",
    [
        "    indented code",
        "\tindented code",
        ">     print('inside code')",
        "<!--\n[hidden](missing.md)\n-->\n",
        "<!DOCTYPE html>\ninternal\n\n",
        "<div>\ninternal\n</div>\n\n",
        "[ref]: missing.md\n    continuation\n",
        "> [ref]: missing.md\n> continuation\n",
        "# Heading",
        "> # Heading",
        "Heading\n---",
        "> Heading\n> ---",
        "***",
        "> ***",
        "hard break  ",
        "hard break \\",
        "hard break \\\\\\",
        "- [ ] internal control",
        "> - [ ] internal control",
        "| table |",
        "escaped \\| pipe",
        "    list continuation",
        ">",
        "*",
        "1.",
        "1)",
    ],
)
def test_target_scanner_excludes_structural_and_unsafe_blocks(report):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        _extract_targets,
    )

    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_target_unavailable",
    ):
        _extract_targets(report)


@pytest.mark.parametrize(
    "report",
    [
        "soft break \\\\",
        "soft break \\\\\\\\",
    ],
)
def test_target_scanner_allows_even_trailing_backslash_runs(report):
    from api.strict_citation_finalization import _extract_targets

    target = _extract_targets(report)[0]

    assert report[target.start : target.end] == report


def test_target_scanner_keeps_simple_container_prose_and_inline_link_bytes():
    from api.strict_citation_finalization import _extract_targets

    report = (
        "- Unordered [kept](https://existing.example/path?q=1)\n"
        "1. Ordered dot\n"
        "1) Ordered parenthesis\n"
        "> Quoted prose"
    )

    targets = _extract_targets(report)

    assert [target.excerpt for target in targets] == report.splitlines()
    for target in targets:
        assert report[target.start : target.end] == target.excerpt
    assert (
        "[kept](https://existing.example/path?q=1)"
        in report[targets[0].start : targets[0].end]
    )


def test_target_scanner_omits_sensitive_paragraph_and_keeps_safe_neighbor():
    from api.strict_citation_finalization import _extract_targets

    report = "Safe paragraph.\n\napi_key=obvious-marker"

    assert [target.excerpt for target in _extract_targets(report)] == [
        "Safe paragraph."
    ]


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


def test_source_projection_requires_current_thread_and_preserves_first_seen():
    from api.strict_citation_finalization import _project_sources

    first = _evidence("https://example.com/first", snippet="first")
    duplicate = _evidence("https://example.com/first", snippet="later")
    wrong_thread = replace(
        _evidence("https://example.com/wrong-thread"),
        thread_id="thread-other",
    )
    second = _evidence("https://example.com/second", snippet="second")

    sources = _project_sources(
        _outcome(evidence=[first, duplicate, wrong_thread, second])
    )

    assert [
        (source.source_id, source.source_url, source.snippet)
        for source in sources
    ] == [
        ("s001", "https://example.com/first", "first"),
        ("s002", "https://example.com/second", "second"),
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/source",
        "https://example.com/source?query=1",
        "https://example.com/source#fragment",
        "https://localhost/source",
        "https://127.0.0.1/source",
        "https://user@example.com/source",
        "https://example.com/" + ("a" * 2040),
        "https://example.com/unsafe<",
        "https://example.com/unsafe>",
        "https://example.com/unsafe\\",
    ],
)
def test_source_projection_rejects_unpublishable_or_unsafe_urls(url):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        _project_sources,
    )

    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_source_unavailable",
    ):
        _project_sources(_outcome(evidence=[_evidence(url)]))


def test_source_projection_accepts_parenthesis_and_caps_deterministic_ids():
    from api.strict_citation_finalization import _project_sources

    evidence = [
        _evidence(f"https://example.com/source/{index}(record")
        for index in range(1, 103)
    ]

    sources = _project_sources(_outcome(evidence=evidence))

    assert len(sources) == 100
    assert sources[0].source_id == "s001"
    assert sources[-1].source_id == "s100"
    assert sources[-1].source_url == "https://example.com/source/100(record"


def test_source_projection_bounds_utf8_snippet_without_splitting_codepoint():
    from api.strict_citation_finalization import _project_sources

    source = _project_sources(
        _outcome(evidence=[_evidence(snippet="界" * 300)])
    )[0]

    assert len(source.snippet.encode("utf-8")) <= 512
    assert source.snippet
    assert set(source.snippet) == {"界"}


@pytest.mark.parametrize(
    "snippet",
    [
        "Authorization: Bearer obvious",
        "api_key=obvious",
        "provider diagnostic: obvious",
        "Traceback: obvious",
        "/Users/example/private",
        "/home/example/private",
        r"C:\private\state",
    ],
)
def test_source_projection_omits_documented_obvious_markers(snippet):
    from api.strict_citation_finalization import _project_sources

    source = _project_sources(
        _outcome(evidence=[_evidence(snippet=snippet)])
    )[0]

    assert source.snippet == "[context omitted]"


def test_source_projection_rejects_citation_round_trip_failure(monkeypatch):
    import api.strict_citation_finalization as finalizer

    monkeypatch.setattr(
        finalizer,
        "is_exact_source_url_cited",
        lambda source_url, report_text: False,
    )

    with pytest.raises(
        finalizer.StrictCitationFinalizationError,
        match="strict_citation_source_unavailable",
    ):
        finalizer._project_sources(_outcome(evidence=[_evidence()]))


def test_source_projection_rejects_generic_artifact_sanitizer_drift(
    monkeypatch,
):
    import api.strict_citation_finalization as finalizer

    monkeypatch.setattr(
        finalizer,
        "build_generic_result_artifact",
        lambda outcome: {
            "kind": "research_report_markdown",
            "content": "sanitized without the admitted URL",
        },
    )

    with pytest.raises(
        finalizer.StrictCitationFinalizationError,
        match="strict_citation_source_unavailable",
    ):
        finalizer._project_sources(_outcome(evidence=[_evidence()]))


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


def test_packet_exact_fields_ids_bounds_and_private_data_exclusions():
    from api.strict_citation_finalization import (
        MAX_PACKET_BYTES,
        PreparedStrictCitation,
        prepare_strict_citation,
    )

    report = "\n\n".join(
        f"Target paragraph {index}." for index in range(1, 129)
    )
    evidence = [
        _evidence(
            f"https://example.com/source/{index}",
            snippet=f"Bounded source context {index}.",
        )
        for index in range(1, 101)
    ] + [
        _evidence(
            "https://example.com/source/not-projected",
            snippet="UNRELATED_EVIDENCE_BODY",
        )
    ]
    outcome = replace(
        _outcome(report=report, evidence=evidence),
        query="QUERY_MUST_NOT_ENTER_PACKET",
        run_id="RUN_ID_MUST_NOT_ENTER_PACKET",
        segment_id="SEGMENT_ID_MUST_NOT_ENTER_PACKET",
    )

    prepared = prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )

    assert isinstance(prepared, PreparedStrictCitation)
    assert len(prepared.targets) == 128
    assert len(prepared.sources) == 100
    assert len({target.target_id for target in prepared.targets}) == 128
    assert len({source.source_id for source in prepared.sources}) == 100
    packet_text = prepared.messages[1].content
    payload = json.loads(packet_text.splitlines()[1])
    assert set(payload) == {"instruction", "schema", "sources", "targets"}
    assert all(set(row) == {"excerpt", "target_id"} for row in payload["targets"])
    assert all(
        set(row) == {"snippet", "source_id", "source_url"}
        for row in payload["sources"]
    )
    assert len(packet_text.encode("utf-8")) <= MAX_PACKET_BYTES
    for forbidden in (
        "QUERY_MUST_NOT_ENTER_PACKET",
        "RUN_ID_MUST_NOT_ENTER_PACKET",
        "SEGMENT_ID_MUST_NOT_ENTER_PACKET",
        "thread-1",
        "UNRELATED_EVIDENCE_BODY",
        "exception",
        "/Users/",
        "/home/",
    ):
        assert forbidden not in packet_text


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
    model = ScriptedChatModel()
    with pytest.raises(StrictCitationFinalizationError, match=code):
        prepare_strict_citation(
            outcome=outcome,
            initial_artifact=build_generic_result_artifact(outcome),
        )
    assert model.call_count == 0


def test_prepare_rejects_fallback_before_any_call():
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        prepare_strict_citation,
    )

    outcome = replace(_outcome(evidence=[_evidence()]), report_candidate=None)
    artifact = build_generic_result_artifact(outcome)
    model = ScriptedChatModel()

    assert artifact["kind"] == "research_report_fallback_markdown"
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_initial_artifact_invalid",
    ):
        prepare_strict_citation(
            outcome=outcome,
            initial_artifact=artifact,
        )
    assert model.call_count == 0


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        "null",
        "1",
        '"scalar"',
        "{}",
        '{"placements":[],"extra":true}',
        '{"placements":[]}',
        '{"placements":null}',
        '{"placements":"not-a-list"}',
        '{"placements":[null]}',
        '{"placements":[{}]}',
        '{"placements":[{"target_id":"t001"}]}',
        '{"placements":[{"source_id":"s001"}]}',
        '{"placements":[{"target_id":1,"source_id":"s001"}]}',
        '{"placements":[{"target_id":"t001","source_id":1}]}',
        '{"placements":[{"target_id":"","source_id":"s001"}]}',
        '{"placements":[{"target_id":"t001","source_id":""}]}',
        '{"placements":[{"target_id":"unknown","source_id":"s001"}]}',
        '{"placements":[{"target_id":"t001","source_id":"unknown"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001","url":"x"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001","markdown":"x"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001","explanation":"x"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001","score":1}]}',
        '{"placements":[{"target_id":"t001","source_id":{"value":"s001"}}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001"},{"target_id":"t001","source_id":"s001"}]}',
        '{"placements":[{"target_id":"t001","source_id":"s001"},{"target_id":"t001","source_id":"s002"}]}',
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


@pytest.mark.parametrize(
    "content",
    [
        None,
        b'{"placements":[]}',
        1,
        chr(0xD800),
        "[" * 2000 + "0" + "]" * 2000,
        " " * (64 * 1024 + 1),
    ],
)
def test_parser_maps_untrusted_type_encoding_depth_and_size_to_closed_code(
    content,
):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        _parse_placements,
    )

    prepared = prepare_for_call()
    with pytest.raises(StrictCitationFinalizationError) as raised:
        _parse_placements(content, prepared.targets, prepared.sources)

    assert raised.value.code == "strict_citation_response_invalid"
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None


def test_parser_accepts_only_the_exact_valid_shape_and_declared_cap():
    from api.strict_citation_finalization import (
        CitationPlacement,
        _parse_placements,
    )

    prepared = prepare_for_call()

    assert _parse_placements(
        '{"placements":[{"target_id":"t001","source_id":"s001"}]}',
        prepared.targets,
        prepared.sources,
    ) == (CitationPlacement("t001", "s001"),)

    excessive_rows = [
        {"target_id": "t001", "source_id": "s001"},
        {"target_id": "t002", "source_id": "s001"},
        {"target_id": "t003", "source_id": "s001"},
    ]
    with pytest.raises(
        RuntimeError,
        match="strict_citation_response_invalid",
    ):
        _parse_placements(
            json.dumps({"placements": excessive_rows}),
            prepared.targets,
            prepared.sources,
        )


def prepare_for_call(report="Supported first.\n\nSupported second."):
    from api.strict_citation_finalization import prepare_strict_citation

    outcome = _outcome(report=report, evidence=[_evidence()])
    return prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )


def test_prepare_rejects_noncanonical_initial_artifact_before_any_call():
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        prepare_strict_citation,
    )

    outcome = _outcome(evidence=[_evidence()])
    model = ScriptedChatModel()

    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_initial_artifact_invalid",
    ):
        prepare_strict_citation(
            outcome=outcome,
            initial_artifact={
                "kind": "research_report_markdown",
                "content": "different bytes",
            },
        )

    assert model.call_count == 0


def test_prepare_eligible_path_builds_only_locked_messages_and_config():
    from api.strict_citation_finalization import (
        PreparedStrictCitation,
        prepare_strict_citation,
    )

    outcome = _outcome(evidence=[_evidence()])
    model = ScriptedChatModel()

    prepared = prepare_strict_citation(
        outcome=outcome,
        initial_artifact=build_generic_result_artifact(outcome),
    )

    assert isinstance(prepared, PreparedStrictCitation)
    assert model.call_count == 0
    assert tuple(type(message) for message in prepared.messages) == (
        SystemMessage,
        HumanMessage,
    )
    assert prepared.messages[1].content.startswith(
        "BEGIN_UNTRUSTED_PACKET\n"
    )
    assert prepared.messages[1].content.endswith(
        "\nEND_UNTRUSTED_PACKET"
    )
    assert set(prepared.config) == {
        "callbacks",
        "run_name",
        "tags",
        "metadata",
    }
    assert prepared.config == {
        "callbacks": [],
        "run_name": "strict-citation-finalization",
        "tags": ["dra:strict-citation-finalization"],
        "metadata": {
            "profile_id": "generic-strict-citation",
            "proof_schema": "dra.strict-citation-profile.v1",
        },
    }


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
    assert result.artifact["kind"] == "research_report_markdown"
    assert model.call_count == 0


def test_renderer_preserves_noninsertion_bytes_and_rejects_stale_basis():
    from api.strict_citation_finalization import (
        CitationPlacement,
        StrictCitationFinalizationError,
        _render_placements,
    )

    report = (
        "First [existing](https://existing.example/a?q=1).\r\n\r\n"
        "Second bytes."
    )
    prepared = prepare_for_call(report)
    target = prepared.targets[0]
    rendered = _render_placements(
        prepared,
        (CitationPlacement(target.target_id, "s001"),),
    )

    canonical = prepared.initial_artifact["content"]
    prefix = canonical[: target.end]
    suffix = canonical[target.end :]
    assert rendered == (
        prefix
        + " [Source](<https://example.com/source>)"
        + suffix
    )

    stale_target = replace(target, basis_sha256="0" * 64)
    stale = replace(
        prepared,
        targets=(stale_target, *prepared.targets[1:]),
    )
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_target_stale",
    ):
        _render_placements(
            stale,
            (CitationPlacement(stale_target.target_id, "s001"),),
        )


def test_renderer_rejects_corrected_artifact_over_one_mib():
    from api.strict_citation_finalization import (
        CitationPlacement,
        StrictCitationFinalizationError,
        _render_placements,
    )

    report = "A" * (1024 * 1024 - 1)
    prepared = prepare_for_call(report)

    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_artifact_invalid",
    ):
        _render_placements(
            prepared,
            (CitationPlacement("t001", "s001"),),
        )


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        HumanMessage(content="not an AI response"),
        AIMessage(content=[{"type": "text", "text": "not a string"}]),
    ],
)
async def test_invoke_rejects_non_ai_or_non_string_response_once(response):
    from api.strict_citation_finalization import (
        StrictCitationFinalizationError,
        invoke_prepared_strict_citation,
    )

    model = ScriptedChatModel(response=response)
    with pytest.raises(
        StrictCitationFinalizationError,
        match="strict_citation_response_invalid",
    ):
        await invoke_prepared_strict_citation(
            prepared=prepare_for_call(),
            chat_model=model,
        )

    assert model.call_count == 1


@pytest.mark.asyncio
async def test_invoke_post_recompute_failure_makes_no_second_call(monkeypatch):
    import api.strict_citation_finalization as finalizer

    model = ScriptedChatModel()
    monkeypatch.setattr(
        finalizer,
        "mark_cited_evidence",
        lambda evidence_entries, report: list(evidence_entries),
    )

    with pytest.raises(
        finalizer.StrictCitationFinalizationError,
        match="strict_citation_invariant_failed",
    ):
        await finalizer.invoke_prepared_strict_citation(
            prepared=prepare_for_call(),
            chat_model=model,
        )

    assert model.call_count == 1
