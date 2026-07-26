"""Strict public-safe contracts for Agent evaluation sensitivity gate v2."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


DATASET_SCHEMA_VERSION = "dra.agent-evaluation-v2-cases.v1"
REPORT_SCHEMA_VERSION = "dra.agent-evaluation-v2-report.v1"
COMPARISON_SCHEMA_VERSION = "dra.agent-evaluation-v2-comparison.v1"
SEMANTIC_COMPARISON_SCHEMA_VERSION = (
    "dra.agent-evaluation-v2-semantic-comparison.v1"
)
CASE_IDS = (
    "trajectory-call-result-pairing",
    "evidence-current-run-reference",
    "safety-untrusted-instruction",
)
CASE_CLASSES = (
    "trajectory_regression",
    "evidence_regression",
    "safety_regression",
)
MUTATION_IDS = (
    "trajectory.call_result_pairing",
    "evidence.current_run_reference",
    "safety.action_after_untrusted_instruction",
)
RESPONSIBLE_EVALUATORS = (
    "trajectory_policy",
    "evidence_integrity",
    "safety_boundary",
)
EXPECTED_CONTROL_FINDINGS = (
    "trajectory.event_invalid",
    "evidence.reference_unresolved",
    "safety.action_after_untrusted_instruction",
)
MAX_DATASET_BYTES = 256 * 1024
MAX_PUBLIC_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024
MAX_COLLECTION_ITEMS = 256
MAX_DEPTH = 16

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CODE_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
_FORBIDDEN_KEYS = {
    "artifact_body",
    "content",
    "credential",
    "exception",
    "password",
    "prompt",
    "query_text",
    "raw_error",
    "raw_evidence",
    "secret",
    "snippet",
    "synthetic_query",
    "synthetic_report_markdown",
    "synthetic_source_text",
    "tool_payload",
    "trace_id",
}
_FORBIDDEN_MARKERS = (
    "/Users/",
    "/home/",
    "/private/",
    "Traceback (most recent call last)",
    "api_key=",
    "credential=",
    "password=",
    "secret=",
)


class EvaluationV2ValidationError(ValueError):
    """Stable library error that never contains untrusted validation detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise EvaluationV2ValidationError(code)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _Policy(_StrictModel):
    requires_evidence: Literal[True]
    allowed_tools: list[Literal["internet_search", "write_file"]]
    blocked_after_untrusted_signal: list[Literal["write_file"]]


class _Event(_StrictModel):
    event_id: str
    kind: Literal["assistant", "tool_call", "tool_result", "terminal"]
    call_id: str | None = None
    tool_name: Literal["internet_search", "write_file"] | None = None
    trust: Literal["trusted", "untrusted"] | None = None

    @model_validator(mode="after")
    def _kind_fields(self) -> "_Event":
        required: dict[str, tuple[str, ...]] = {
            "assistant": (),
            "terminal": (),
            "tool_call": ("call_id", "tool_name"),
            "tool_result": ("call_id", "trust"),
        }
        allowed = set(required[self.kind])
        values = {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "trust": self.trust,
        }
        if any(values[name] is None for name in allowed):
            raise ValueError("missing event field")
        if any(value is not None and name not in allowed for name, value in values.items()):
            raise ValueError("unexpected event field")
        return self


class _TrustSignal(_StrictModel):
    event_id: str
    signal: Literal["untrusted_instruction_present"]


class _TokenUsage(_StrictModel):
    status: Literal["observed"]
    input_tokens: int = Field(ge=0, le=100_000)
    output_tokens: int = Field(ge=0, le=100_000)


class _Metrics(_StrictModel):
    assistant_messages: int = Field(ge=0, le=64)
    tool_calls: int = Field(ge=0, le=64)
    elapsed_ms: int = Field(ge=0, le=300_000)
    token_usage: _TokenUsage


class _Expected(_StrictModel):
    blocking_finding_codes: list[str]
    observational_finding_codes: list[str]


class _Artifact(_StrictModel):
    artifact_id: str
    kind: Literal["decision_brief"]
    media_type: Literal["text/markdown"]


class _Case(_StrictModel):
    case_id: str
    case_class: str
    mutation_id: str
    responsible_evaluator: str
    expected_control_finding: str
    synthetic_query: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    synthetic_source_text: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    synthetic_report_markdown: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    source_url: str = Field(min_length=1, max_length=512)
    artifact: _Artifact
    policy: _Policy
    trajectory: list[_Event] = Field(min_length=4, max_length=16)
    trust_signals: list[_TrustSignal] = Field(max_length=4)
    metrics: _Metrics
    expected: _Expected

    @model_validator(mode="after")
    def _semantic_shape(self) -> "_Case":
        event_ids = [event.event_id for event in self.trajectory]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("duplicate event")
        if self.trajectory[-1].kind != "terminal":
            raise ValueError("terminal must be last")
        calls = [event.call_id for event in self.trajectory if event.kind == "tool_call"]
        results = [
            event.call_id for event in self.trajectory if event.kind == "tool_result"
        ]
        if calls != results or len(calls) != len(set(calls)):
            raise ValueError("call/result mismatch")
        if self.metrics.assistant_messages != sum(
            event.kind == "assistant" for event in self.trajectory
        ):
            raise ValueError("assistant metric mismatch")
        if self.metrics.tool_calls != len(calls):
            raise ValueError("tool metric mismatch")
        if any(signal.event_id not in event_ids for signal in self.trust_signals):
            raise ValueError("unknown trust signal")
        return self


class _Dataset(_StrictModel):
    schema_version: Literal["dra.agent-evaluation-v2-cases.v1"]
    cases: list[_Case] = Field(min_length=3, max_length=3)


class _DatasetRef(_StrictModel):
    schema_version: Literal["dra.agent-evaluation-v2-cases.v1"]
    sha256: str
    case_ids: list[str]


class _Summary(_StrictModel):
    pair_count: int = Field(ge=0, le=3)
    healthy_anchor_count: int = Field(ge=0, le=6)
    sensitive_pair_count: int = Field(ge=0, le=3)
    gate_passed: bool


class _Report(_StrictModel):
    schema_version: Literal["dra.agent-evaluation-v2-report.v1"]
    dataset: _DatasetRef
    pairs: list[dict[str, Any]] = Field(max_length=3)
    summary: _Summary
    limits: list[str] = Field(min_length=1, max_length=32)
    non_claims: list[str] = Field(min_length=1, max_length=32)


class _Comparison(_StrictModel):
    schema_version: Literal["dra.agent-evaluation-v2-comparison.v1"]
    match: bool
    gate_passed: bool
    changed_case_ids: list[str]
    false_green_case_ids: list[str]
    observed_declared_control_finding_codes: list[str]
    unexpected_blocking_finding_codes: list[str]


def _plain(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _validate_finite_and_bounded(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        _fail("evaluation_v2_public_output_unsafe")
    if isinstance(value, bool) or value is None or isinstance(value, str):
        if isinstance(value, str) and len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            _fail("evaluation_v2_public_output_unsafe")
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("evaluation_v2_public_output_unsafe")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            _fail("evaluation_v2_public_output_unsafe")
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("evaluation_v2_public_output_unsafe")
            _validate_finite_and_bounded(item, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COLLECTION_ITEMS:
            _fail("evaluation_v2_public_output_unsafe")
        for item in value:
            _validate_finite_and_bounded(item, depth=depth + 1)
        return
    _fail("evaluation_v2_public_output_unsafe")


def validate_public_projection(value: Any) -> Any:
    _validate_finite_and_bounded(value)

    def scan(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key.lower() in _FORBIDDEN_KEYS:
                    _fail("evaluation_v2_public_output_unsafe")
                scan(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                scan(child)
        elif isinstance(item, str) and any(
            marker.lower() in item.lower() for marker in _FORBIDDEN_MARKERS
        ):
            _fail("evaluation_v2_public_output_unsafe")

    scan(value)
    return value


def _validate_case_identities(cases: list[dict[str, Any]]) -> None:
    identities = [
        (
            case["case_id"],
            case["case_class"],
            case["mutation_id"],
            case["responsible_evaluator"],
            case["expected_control_finding"],
        )
        for case in cases
    ]
    expected = list(
        zip(
            CASE_IDS,
            CASE_CLASSES,
            MUTATION_IDS,
            RESPONSIBLE_EVALUATORS,
            EXPECTED_CONTROL_FINDINGS,
            strict=True,
        )
    )
    if identities != expected:
        _fail("evaluation_v2_case_invalid")
    for case in cases:
        for value in (
            case["case_id"],
            case["mutation_id"],
            case["responsible_evaluator"],
        ):
            if not _IDENTIFIER_RE.fullmatch(value):
                _fail("evaluation_v2_case_invalid")
        if not _CODE_RE.fullmatch(case["expected_control_finding"]):
            _fail("evaluation_v2_case_invalid")


def validate_dataset(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        canonical = _plain(_Dataset.model_validate(value))
    except (ValidationError, TypeError, ValueError):
        _fail("evaluation_v2_dataset_invalid")
    _validate_case_identities(canonical["cases"])
    _validate_finite_and_bounded(canonical)
    return canonical


def load_dataset(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_DATASET_BYTES or not raw.endswith(b"\n"):
            _fail("evaluation_v2_dataset_invalid")
        value = json.loads(raw)
    except EvaluationV2ValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("evaluation_v2_dataset_invalid")
    return validate_dataset(value)


def canonical_json_bytes(value: Any) -> bytes:
    _validate_finite_and_bounded(value)
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError):
        _fail("evaluation_v2_public_output_unsafe")


def dataset_hash(dataset: Mapping[str, Any]) -> str:
    canonical = validate_dataset(dataset)
    basis = {
        "hash_domain": "dra.agent-evaluation-v2-dataset-hash.v1",
        "schema_version": canonical["schema_version"],
        "cases": canonical["cases"],
    }
    return hashlib.sha256(canonical_json_bytes(basis)).hexdigest()


def validate_report(value: Mapping[str, Any]) -> dict[str, Any]:
    validate_public_projection(value)
    try:
        canonical = _plain(_Report.model_validate(value))
    except (ValidationError, TypeError, ValueError):
        _fail("evaluation_v2_report_invalid")
    dataset = canonical["dataset"]
    if dataset["case_ids"] != list(CASE_IDS) or not _SHA256_RE.fullmatch(
        dataset["sha256"]
    ):
        _fail("evaluation_v2_report_invalid")
    return canonical


def validate_comparison(value: Mapping[str, Any]) -> dict[str, Any]:
    validate_public_projection(value)
    try:
        canonical = _plain(_Comparison.model_validate(value))
    except (ValidationError, TypeError, ValueError):
        _fail("evaluation_v2_report_invalid")
    for field in (
        "changed_case_ids",
        "false_green_case_ids",
    ):
        if any(case_id not in CASE_IDS for case_id in canonical[field]):
            _fail("evaluation_v2_report_invalid")
    return canonical
