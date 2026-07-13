"""Strict structural contracts for the deterministic Agent evaluation gate."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError


MANIFEST_SCHEMA_VERSION = "dra.agent-evaluation-cases.v1"
REPORT_SCHEMA_VERSION = "dra.agent-evaluation-report.v1"
COMPARISON_SCHEMA_VERSION = "dra.agent-evaluation-comparison.v1"
EVALUATOR_VERSION = "1"
MAX_MANIFEST_BYTES = 512 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
CASE_IDS = (
    "canonical_success",
    "fallback_blocked",
    "review_required",
    "failed_terminal",
    "evidence_missing",
    "prohibited_tool",
    "untrusted_instruction_action",
    "cross_run_reference",
)
REGISTRY = (
    ("result_contract", "1"),
    ("trajectory_policy", "1"),
    ("evidence_integrity", "1"),
    ("terminal_state", "1"),
    ("safety_boundary", "1"),
    ("efficiency_observation", "1"),
)

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CODE_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
_AMOUNT_RE = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{8}\Z")
_CURRENCY_RE = re.compile(r"[A-Z]{3}\Z")
_PRICING_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_KEYS = {
    "query",
    "prompt",
    "content",
    "snippet",
    "arguments",
    "tool_payload",
    "raw_error",
}
_FORBIDDEN_MARKERS = (
    "/Users/",
    "/private/",
    "/home/",
    "Traceback",
    "api_key=",
    "secret=",
)


class EvaluationValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise EvaluationValidationError(code)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ManifestEnvelope(StrictModel):
    schema_version: str
    cases: list[dict[str, Any]]


class ExpectedModel(StrictModel):
    blocking_finding_codes: list[str]
    observational_finding_codes: list[str]


class CostEstimateModel(StrictModel):
    amount: str
    currency: str
    pricing_basis: str
    estimate: Literal[True]


class ObservedTokenUsageModel(StrictModel):
    status: Literal["observed"]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_estimate: CostEstimateModel


class MissingTokenUsageModel(StrictModel):
    status: Literal["not_observed"]


TokenUsageModel = Annotated[
    Union[ObservedTokenUsageModel, MissingTokenUsageModel], Field(discriminator="status")
]


class MetricsModel(StrictModel):
    assistant_messages: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    token_usage: TokenUsageModel


class ManifestEventBase(StrictModel):
    event_id: str
    run_ref: Literal["current", "foreign"]


class ManifestAssistantEvent(ManifestEventBase):
    kind: Literal["assistant"]


class ManifestToolCallEvent(ManifestEventBase):
    kind: Literal["tool_call"]
    call_id: str
    tool_name: str


class ManifestToolResultEvent(ManifestEventBase):
    kind: Literal["tool_result"]
    call_id: str
    trust: Literal["trusted", "untrusted"]


class ManifestTerminalEvent(ManifestEventBase):
    kind: Literal["terminal"]


ManifestEvent = Annotated[
    Union[
        ManifestAssistantEvent,
        ManifestToolCallEvent,
        ManifestToolResultEvent,
        ManifestTerminalEvent,
    ],
    Field(discriminator="kind"),
]


class TrustSignalModel(StrictModel):
    event_id: str
    signal: Literal["untrusted_instruction_present"]


class CaseEnvelope(StrictModel):
    case_id: str
    source_case_id: str
    evidence_mode: Literal["source", "empty"]
    requires_evidence: bool
    allowed_tools: list[str]
    blocked_after_untrusted_signal: list[str]
    trajectory_status: Literal["complete"]
    trajectory: list[dict[str, Any]]
    evidence_ref_status: Literal["not_observed"]
    typed_evidence_refs: list[str]
    trust_signal_status: Literal["observed"]
    trust_signals: list[TrustSignalModel]
    metrics: dict[str, Any]
    expected: ExpectedModel


class CaseModel(StrictModel):
    case_id: str
    source_case_id: str
    evidence_mode: Literal["source", "empty"]
    requires_evidence: bool
    allowed_tools: list[str]
    blocked_after_untrusted_signal: list[str]
    trajectory_status: Literal["complete"]
    trajectory: list[ManifestEvent]
    evidence_ref_status: Literal["not_observed"]
    typed_evidence_refs: list[str]
    trust_signal_status: Literal["observed"]
    trust_signals: list[TrustSignalModel]
    metrics: MetricsModel
    expected: ExpectedModel


class RuntimeEventBase(StrictModel):
    event_id: str
    run_id: str


class RuntimeAssistantEvent(RuntimeEventBase):
    kind: Literal["assistant"]


class RuntimeToolCallEvent(RuntimeEventBase):
    kind: Literal["tool_call"]
    call_id: str
    tool_name: str


class RuntimeToolResultEvent(RuntimeEventBase):
    kind: Literal["tool_result"]
    call_id: str
    trust: Literal["trusted", "untrusted"]


class RuntimeTerminalEvent(RuntimeEventBase):
    kind: Literal["terminal"]


RuntimeEvent = Annotated[
    Union[
        RuntimeAssistantEvent,
        RuntimeToolCallEvent,
        RuntimeToolResultEvent,
        RuntimeTerminalEvent,
    ],
    Field(discriminator="kind"),
]


class PolicyModel(StrictModel):
    requires_evidence: bool
    allowed_tools: list[str]
    blocked_after_untrusted_signal: list[str]


class ObservationEnvelope(StrictModel):
    case_id: str
    source: Literal["deterministic"]
    run: dict[str, Any]
    evidence: list[dict[str, Any]]
    result: dict[str, Any]
    trajectory_status: Literal["complete"]
    trajectory: list[dict[str, Any]]
    evidence_ref_status: Literal["not_observed", "observed"]
    typed_evidence_refs: list[str]
    trust_signal_status: Literal["observed"]
    trust_signals: list[TrustSignalModel]
    policy: PolicyModel
    metrics: dict[str, Any]
    expected: ExpectedModel


class ObservationModel(StrictModel):
    case_id: str
    source: Literal["deterministic"]
    run: dict[str, Any]
    evidence: list[dict[str, Any]]
    result: dict[str, Any]
    trajectory_status: Literal["complete"]
    trajectory: list[RuntimeEvent]
    evidence_ref_status: Literal["not_observed", "observed"]
    typed_evidence_refs: list[str]
    trust_signal_status: Literal["observed"]
    trust_signals: list[TrustSignalModel]
    policy: PolicyModel
    metrics: MetricsModel
    expected: ExpectedModel


class FindingModel(StrictModel):
    evaluator_id: str
    code: str
    severity: Literal["blocking", "observational"]


class EvaluatorResultModel(StrictModel):
    evaluator_id: str
    status: Literal["pass", "expected_block", "regression", "not_observed"]
    finding_codes: list[str]


class EvaluatedCaseModel(StrictModel):
    case_id: str
    status: Literal["pass", "expected_block", "regression", "not_observed"]
    expectation_match: bool
    expected: ExpectedModel
    evaluators: list[EvaluatorResultModel]
    blocking_finding_codes: list[str]
    observational_finding_codes: list[str]
    findings: list[FindingModel]
    metrics: MetricsModel


class DatasetModel(StrictModel):
    schema_version: Literal[MANIFEST_SCHEMA_VERSION]
    sha256: str
    case_ids: list[str]


class RegistryEntryModel(StrictModel):
    evaluator_id: str
    version: Literal["1"]


class SummaryModel(StrictModel):
    blocking_regression_count: int = Field(ge=0)
    expectation_mismatch_count: int = Field(ge=0)
    observational_change_count: int = Field(ge=0)
    not_observed_count: int = Field(ge=0)
    release_gate_passed: bool


class ReportEnvelope(StrictModel):
    schema_version: str
    evaluator_version: Literal["1"]
    source: Literal["deterministic"]
    dataset: DatasetModel
    registry: list[RegistryEntryModel]
    summary: SummaryModel
    cases: list[EvaluatedCaseModel]
    limits: list[str]


class HashPairModel(StrictModel):
    json_sha256: str
    markdown_sha256: str


class ComparisonEnvelope(StrictModel):
    schema_version: str
    match: bool
    candidate: HashPairModel
    baseline: HashPairModel
    changed_case_ids: list[str]
    blocking_regression_codes: list[str]
    observational_changes: list[str]


def _model_dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _validate_identifier(value: str, code: str) -> None:
    if not _IDENTIFIER_RE.fullmatch(value):
        _fail(code)


def _validate_metrics(payload: Any) -> dict[str, Any]:
    try:
        model = MetricsModel.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_metrics_invalid")
    canonical = _model_dump(model)
    token_usage = canonical["token_usage"]
    if token_usage["status"] == "observed":
        estimate = token_usage["cost_estimate"]
        if (
            not _AMOUNT_RE.fullmatch(estimate["amount"])
            or not _CURRENCY_RE.fullmatch(estimate["currency"])
            or not _PRICING_RE.fullmatch(estimate["pricing_basis"])
        ):
            _fail("evaluation_metrics_invalid")
    return canonical


def _validate_codes(expected: dict[str, Any], code: str) -> None:
    for value in (
        expected["blocking_finding_codes"]
        + expected["observational_finding_codes"]
    ):
        if not _CODE_RE.fullmatch(value):
            _fail(code)


def _validate_case(payload: Any) -> dict[str, Any]:
    try:
        envelope = CaseEnvelope.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_case_invalid")
    raw = envelope.model_dump(mode="python")
    raw["metrics"] = _validate_metrics(raw["metrics"])
    try:
        model = CaseModel.model_validate(raw, strict=True)
    except ValidationError:
        _fail("evaluation_case_invalid")
    canonical = _model_dump(model)
    for value in (
        canonical["case_id"],
        canonical["source_case_id"],
        *canonical["allowed_tools"],
        *canonical["blocked_after_untrusted_signal"],
    ):
        _validate_identifier(value, "evaluation_case_invalid")
    event_ids = [event["event_id"] for event in canonical["trajectory"]]
    if len(event_ids) != len(set(event_ids)):
        _fail("evaluation_case_invalid")
    for event in canonical["trajectory"]:
        for key in ("event_id", "call_id", "tool_name"):
            if key in event:
                _validate_identifier(event[key], "evaluation_case_invalid")
    result_events = {
        event["event_id"]
        for event in canonical["trajectory"]
        if event["kind"] == "tool_result"
    }
    if any(signal["event_id"] not in result_events for signal in canonical["trust_signals"]):
        _fail("evaluation_case_invalid")
    if canonical["typed_evidence_refs"]:
        _fail("evaluation_case_invalid")
    _validate_codes(canonical["expected"], "evaluation_case_invalid")
    return canonical


def validate_manifest(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("schema_version") not in {
        None,
        MANIFEST_SCHEMA_VERSION,
    }:
        _fail("evaluation_schema_unsupported")
    try:
        envelope = ManifestEnvelope.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_manifest_invalid")
    if envelope.schema_version != MANIFEST_SCHEMA_VERSION:
        _fail("evaluation_schema_unsupported")
    cases = [_validate_case(case) for case in envelope.cases]
    if [case["case_id"] for case in cases] != list(CASE_IDS):
        _fail("evaluation_case_invalid")
    canonical = {"schema_version": MANIFEST_SCHEMA_VERSION, "cases": cases}
    assert_public_safe(canonical)
    return canonical


def validate_observation(payload: Any) -> dict[str, Any]:
    try:
        envelope = ObservationEnvelope.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_case_invalid")
    raw = envelope.model_dump(mode="python")
    raw["metrics"] = _validate_metrics(raw["metrics"])
    try:
        model = ObservationModel.model_validate(raw, strict=True)
    except ValidationError:
        _fail("evaluation_case_invalid")
    canonical = _model_dump(model)
    _validate_identifier(canonical["case_id"], "evaluation_case_invalid")
    event_ids = [event["event_id"] for event in canonical["trajectory"]]
    if len(event_ids) != len(set(event_ids)):
        _fail("evaluation_case_invalid")
    for event in canonical["trajectory"]:
        _validate_identifier(event["event_id"], "evaluation_case_invalid")
        _validate_identifier(event["run_id"], "evaluation_case_invalid")
        for key in ("call_id", "tool_name"):
            if key in event:
                _validate_identifier(event[key], "evaluation_case_invalid")
    result_events = {
        event["event_id"]
        for event in canonical["trajectory"]
        if event["kind"] == "tool_result"
    }
    if any(signal["event_id"] not in result_events for signal in canonical["trust_signals"]):
        _fail("evaluation_case_invalid")
    _validate_codes(canonical["expected"], "evaluation_case_invalid")
    return canonical


def validate_report(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("schema_version") not in {
        None,
        REPORT_SCHEMA_VERSION,
    }:
        _fail("evaluation_schema_unsupported")
    if isinstance(payload, dict) and "registry" in payload:
        registry = payload["registry"]
        expected = [
            {"evaluator_id": evaluator_id, "version": version}
            for evaluator_id, version in REGISTRY
        ]
        if registry != expected:
            _fail("evaluation_registry_invalid")
    try:
        model = ReportEnvelope.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_output_invalid")
    if model.schema_version != REPORT_SCHEMA_VERSION:
        _fail("evaluation_schema_unsupported")
    canonical = _model_dump(model)
    if not _SHA256_RE.fullmatch(canonical["dataset"]["sha256"]):
        _fail("evaluation_output_invalid")
    for case in canonical["cases"]:
        _validate_codes(case["expected"], "evaluation_output_invalid")
        for finding in case["findings"]:
            if not _CODE_RE.fullmatch(finding["code"]):
                _fail("evaluation_output_invalid")
    assert_public_safe(canonical)
    return canonical


def validate_comparison(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("schema_version") not in {
        None,
        COMPARISON_SCHEMA_VERSION,
    }:
        _fail("evaluation_schema_unsupported")
    try:
        model = ComparisonEnvelope.model_validate(payload, strict=True)
    except ValidationError:
        _fail("evaluation_output_invalid")
    if model.schema_version != COMPARISON_SCHEMA_VERSION:
        _fail("evaluation_schema_unsupported")
    canonical = _model_dump(model)
    for side in ("candidate", "baseline"):
        for value in canonical[side].values():
            if not _SHA256_RE.fullmatch(value):
                _fail("evaluation_output_invalid")
    assert_public_safe(canonical)
    return canonical


def assert_public_safe(payload: Any) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if any(key in _FORBIDDEN_KEYS for key in value):
                _fail("evaluation_public_output_unsafe")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
        elif isinstance(value, str) and any(marker in value for marker in _FORBIDDEN_MARKERS):
            _fail("evaluation_public_output_unsafe")

    visit(payload)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            _fail("evaluation_manifest_invalid")
        payload = json.loads(raw.decode("utf-8"))
    except EvaluationValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("evaluation_manifest_invalid")
    return validate_manifest(payload)


def serialize_json(
    payload: dict[str, Any], *, validator: Callable[[Any], dict[str, Any]]
) -> bytes:
    canonical = validator(payload)
    return (
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def dataset_hash(manifest: dict[str, Any]) -> str:
    canonical = validate_manifest(manifest)
    raw = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
