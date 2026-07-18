"""Strict contracts for the bounded live producer evaluation harness."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


MANIFEST_SCHEMA_VERSION = "dra.bounded-live-producer-manifest.v1"
REPORT_SCHEMA_VERSION = "dra.bounded-live-producer-evaluation.v1"
ERROR_SCHEMA_VERSION = "dra.bounded-live-producer-evaluation-error.v1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PUBLIC_BYTES = 1024 * 1024

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_DOMAIN_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_VERSION_RE = re.compile(
    r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}\Z",
    re.ASCII,
)
_AMOUNT_RE = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{8}\Z", re.ASCII)
_CURRENCY_RE = re.compile(r"[A-Z]{3}\Z", re.ASCII)
_HOST_ABSOLUTE_PATH_RE = re.compile(
    r"(?:(?:/Users|/private|/var|/tmp|/Volumes|/home|/opt)/[^\s)\"']+)"
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\s\"'])[A-Za-z]:[\\/]")
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "query",
        "scope",
        "content",
        "snippet",
        "tool_payload",
        "raw_error",
        "traceback",
        "local_path",
        "port",
        "project_name",
        "container_name",
        "volume_name",
        "network_name",
        "idempotency_key",
        "api_key",
    }
)
_FORBIDDEN_PUBLIC_MARKERS = (
    "/Users/",
    "/private/",
    "/home/",
    "/tmp/",
    "Traceback",
    "api_key=",
    "secret=",
    "authorization: bearer",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "LANGSMITH_API_KEY",
)


class EvaluationValidationError(ValueError):
    """Stable in-memory validation error that is never serialized directly."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validation_fail(code: str) -> None:
    raise EvaluationValidationError(code)


class FailurePhase(str, Enum):
    INPUT = "input"
    DOCKER = "docker"
    CREATE = "create"
    OBSERVE = "observe"
    RESULT = "result"
    EVIDENCE = "evidence"
    USAGE = "usage"
    RESTART = "restart"
    REPLAY = "replay"
    OUTPUT = "output"
    CLEANUP = "cleanup"
    INTERNAL = "internal"


class FailureCode(str, Enum):
    MANIFEST_INVALID = "manifest_invalid"
    SOURCE_DIRTY = "source_dirty"
    SOURCE_IDENTITY_INVALID = "source_identity_invalid"
    CREDENTIAL_SOURCE_INVALID = "credential_source_invalid"
    OUTPUT_INVALID = "output_invalid"
    DOCKER_UNAVAILABLE = "docker_unavailable"
    COMPOSE_CONFIG_INVALID = "compose_config_invalid"
    SOURCE_ARCHIVE_INVALID = "source_archive_invalid"
    IMAGE_BUILD_FAILED = "image_build_failed"
    SERVICE_START_FAILED = "service_start_failed"
    SERVICE_IDENTITY_INVALID = "service_identity_invalid"
    CREATE_REJECTED = "create_rejected"
    CREATE_RESPONSE_INVALID = "create_response_invalid"
    CREATE_IDENTITY_MISMATCH = "create_identity_mismatch"
    CREATE_RECONCILIATION_UNRESOLVED = "create_reconciliation_unresolved"
    RUN_OBSERVATION_DEADLINE = "run_observation_deadline"
    RUN_STATE_INVALID = "run_state_invalid"
    RUN_FAILED = "run_failed"
    RUN_FALLBACK_REJECTED = "run_fallback_rejected"
    RUN_DELIVERY_NOT_READY = "run_delivery_not_ready"
    CONSUMER_PROJECTION_INVALID = "consumer_projection_invalid"
    ARTIFACT_INVALID = "artifact_invalid"
    ARTIFACT_HASH_MISMATCH = "artifact_hash_mismatch"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_INVALID = "evidence_invalid"
    EVIDENCE_DOMAIN_REJECTED = "evidence_domain_rejected"
    REQUIRED_CITED_DOMAIN_MISSING = "required_cited_domain_missing"
    USAGE_INVALID = "usage_invalid"
    BACKEND_RESTART_FAILED = "backend_restart_failed"
    RESTART_IDENTITY_DRIFT = "restart_identity_drift"
    RESTART_EVIDENCE_DRIFT = "restart_evidence_drift"
    RESTART_ARTIFACT_DRIFT = "restart_artifact_drift"
    IDEMPOTENT_REPLAY_INVALID = "idempotent_replay_invalid"
    DUPLICATE_RUN_OBSERVED = "duplicate_run_observed"
    REPORT_INVALID = "report_invalid"
    OUTPUT_EXISTS = "output_exists"
    OUTPUT_WRITE_FAILED = "output_write_failed"
    CLEANUP_FAILED = "cleanup_failed"
    EVALUATION_INTERNAL_ERROR = "evaluation_internal_error"


class CleanupStatus(str, Enum):
    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


FAILURE_REGISTRY: dict[FailurePhase, frozenset[FailureCode]] = {
    FailurePhase.INPUT: frozenset(
        {
            FailureCode.MANIFEST_INVALID,
            FailureCode.SOURCE_DIRTY,
            FailureCode.SOURCE_IDENTITY_INVALID,
            FailureCode.CREDENTIAL_SOURCE_INVALID,
            FailureCode.OUTPUT_INVALID,
        }
    ),
    FailurePhase.DOCKER: frozenset(
        {
            FailureCode.DOCKER_UNAVAILABLE,
            FailureCode.COMPOSE_CONFIG_INVALID,
            FailureCode.SOURCE_ARCHIVE_INVALID,
            FailureCode.IMAGE_BUILD_FAILED,
            FailureCode.SERVICE_START_FAILED,
            FailureCode.SERVICE_IDENTITY_INVALID,
        }
    ),
    FailurePhase.CREATE: frozenset(
        {
            FailureCode.CREATE_REJECTED,
            FailureCode.CREATE_RESPONSE_INVALID,
            FailureCode.CREATE_IDENTITY_MISMATCH,
            FailureCode.CREATE_RECONCILIATION_UNRESOLVED,
        }
    ),
    FailurePhase.OBSERVE: frozenset(
        {
            FailureCode.RUN_OBSERVATION_DEADLINE,
            FailureCode.RUN_STATE_INVALID,
            FailureCode.RUN_FAILED,
            FailureCode.RUN_FALLBACK_REJECTED,
            FailureCode.RUN_DELIVERY_NOT_READY,
        }
    ),
    FailurePhase.RESULT: frozenset(
        {
            FailureCode.CONSUMER_PROJECTION_INVALID,
            FailureCode.ARTIFACT_INVALID,
            FailureCode.ARTIFACT_HASH_MISMATCH,
        }
    ),
    FailurePhase.EVIDENCE: frozenset(
        {
            FailureCode.EVIDENCE_MISSING,
            FailureCode.EVIDENCE_INVALID,
            FailureCode.EVIDENCE_DOMAIN_REJECTED,
            FailureCode.REQUIRED_CITED_DOMAIN_MISSING,
        }
    ),
    FailurePhase.USAGE: frozenset({FailureCode.USAGE_INVALID}),
    FailurePhase.RESTART: frozenset(
        {
            FailureCode.BACKEND_RESTART_FAILED,
            FailureCode.RESTART_IDENTITY_DRIFT,
            FailureCode.RESTART_EVIDENCE_DRIFT,
            FailureCode.RESTART_ARTIFACT_DRIFT,
        }
    ),
    FailurePhase.REPLAY: frozenset(
        {FailureCode.IDEMPOTENT_REPLAY_INVALID, FailureCode.DUPLICATE_RUN_OBSERVED}
    ),
    FailurePhase.OUTPUT: frozenset(
        {
            FailureCode.REPORT_INVALID,
            FailureCode.OUTPUT_EXISTS,
            FailureCode.OUTPUT_WRITE_FAILED,
        }
    ),
    FailurePhase.CLEANUP: frozenset({FailureCode.CLEANUP_FAILED}),
    FailurePhase.INTERNAL: frozenset({FailureCode.EVALUATION_INTERNAL_ERROR}),
}


class EvaluationError(Exception):
    """Typed operational failure with a validated public projection."""

    __slots__ = ("code", "phase", "retryable", "cleanup_status")

    def __init__(
        self,
        code: FailureCode | str,
        phase: FailurePhase | str,
        retryable: bool,
        cleanup_status: CleanupStatus | str = CleanupStatus.NOT_STARTED,
    ) -> None:
        try:
            validated_code = FailureCode(code)
            validated_phase = FailurePhase(phase)
            validated_cleanup = CleanupStatus(cleanup_status)
        except ValueError as exc:
            raise ValueError("evaluation_error_invalid") from exc
        if type(retryable) is not bool or validated_code not in FAILURE_REGISTRY[
            validated_phase
        ]:
            raise ValueError("evaluation_error_invalid")
        super().__init__(validated_code.value)
        self.code = validated_code
        self.phase = validated_phase
        self.retryable = retryable
        self.cleanup_status = validated_cleanup


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


_EXPECTED_BOUNDS = {
    "query_utf8_bytes_min": 1,
    "query_utf8_bytes_max": 4096,
    "scope_utf8_bytes_max": 16384,
    "scope_depth_max": 8,
    "scope_nodes_max": 256,
    "required_domains_min": 1,
    "required_domains_max": 8,
    "idempotency_key_ascii_length_min": 8,
    "idempotency_key_ascii_length_max": 128,
    "idempotency_key_entropy_bits_min": 128,
    "archive_bytes_max": 67108864,
    "archive_members_max": 4096,
    "archive_member_bytes_max": 16777216,
    "subprocess_stream_bytes_max": 1048576,
    "http_response_bytes_max": 2097152,
    "artifact_utf8_bytes_min": 1,
    "artifact_utf8_bytes_max": 1048576,
    "evidence_count_min": 1,
    "evidence_count_max": 100,
    "public_json_bytes_max": 1048576,
    "public_markdown_bytes_max": 1048576,
    "docker_probe_seconds": 30,
    "active_lifecycle_seconds": 3300,
    "build_start_seconds": 1200,
    "research_seconds": 1800,
    "restart_replay_seconds": 300,
    "cleanup_seconds": 120,
    "total_wall_seconds": 3450,
}


class TerminalPolicy(StrictModel):
    execution_status: Literal["completed"]
    review_status: Literal["not_required"]
    delivery_status: Literal["ready"]
    failure_cause: None
    artifact_id: Literal["research-report.md"]
    artifact_kind: Literal["research_report_markdown"]
    artifact_media_type: Literal["text/markdown"]
    consumer_support: Literal["supported"]
    consumer_disposition: Literal["accept_draft"]


class ManifestBounds(StrictModel):
    query_utf8_bytes_min: int
    query_utf8_bytes_max: int
    scope_utf8_bytes_max: int
    scope_depth_max: int
    scope_nodes_max: int
    required_domains_min: int
    required_domains_max: int
    idempotency_key_ascii_length_min: int
    idempotency_key_ascii_length_max: int
    idempotency_key_entropy_bits_min: int
    archive_bytes_max: int
    archive_members_max: int
    archive_member_bytes_max: int
    subprocess_stream_bytes_max: int
    http_response_bytes_max: int
    artifact_utf8_bytes_min: int
    artifact_utf8_bytes_max: int
    evidence_count_min: int
    evidence_count_max: int
    public_json_bytes_max: int
    public_markdown_bytes_max: int
    docker_probe_seconds: int
    active_lifecycle_seconds: int
    build_start_seconds: int
    research_seconds: int
    restart_replay_seconds: int
    cleanup_seconds: int
    total_wall_seconds: int

    @model_validator(mode="after")
    def require_exact_values(self) -> "ManifestBounds":
        if self.model_dump(mode="python") != _EXPECTED_BOUNDS:
            raise ValueError("manifest_bounds_invalid")
        return self


class UsagePolicy(StrictModel):
    token_usage: Literal["observed_or_not_observed"]
    cost_estimate: Literal["observed_or_not_observed"]
    search_cost: Literal["not_observed"]
    durable_usage: Literal["not_claimed"]
    provider_invoice: Literal["not_claimed"]


class OutputPolicy(StrictModel):
    json_path: Literal["docs/evidence/bounded-live-producer-v1.json"]
    markdown_path: Literal["docs/evidence/bounded-live-producer-v1.md"]
    overwrite: Literal[False]


NON_CLAIMS = (
    "downstream_business_acceptance",
    "source_truth_or_independent_verification",
    "exactly_once_execution_or_provider_side_effects",
    "running_execution_recovery",
    "multi_instance_high_availability",
    "durable_usage_or_provider_billing",
    "hosted_production_or_sla",
)


def _scope_shape(value: Any, *, depth: int = 1) -> tuple[int, int]:
    if depth > _EXPECTED_BOUNDS["scope_depth_max"]:
        raise ValueError("manifest_scope_invalid")
    if type(value) is dict:
        nodes = 1
        maximum = depth
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("manifest_scope_invalid")
            nested_nodes, nested_depth = _scope_shape(nested, depth=depth + 1)
            nodes += nested_nodes
            maximum = max(maximum, nested_depth)
        return nodes, maximum
    if type(value) is list:
        nodes = 1
        maximum = depth
        for nested in value:
            nested_nodes, nested_depth = _scope_shape(nested, depth=depth + 1)
            nodes += nested_nodes
            maximum = max(maximum, nested_depth)
        return nodes, maximum
    if value is None or type(value) in {str, int, float, bool}:
        if type(value) is float and (value != value or value in {float("inf"), float("-inf")}):
            raise ValueError("manifest_scope_invalid")
        return 1, depth
    raise ValueError("manifest_scope_invalid")


def _validate_domain(value: str) -> str:
    if not _DOMAIN_RE.fullmatch(value) or value.endswith((".local", ".internal")):
        raise ValueError("domain_invalid")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("domain_invalid")


class ManifestModel(StrictModel):
    schema_version: Literal["dra.bounded-live-producer-manifest.v1"]
    scenario_id: Literal["cpython-313-free-threaded-pilot"]
    profile_id: Literal["generic"]
    query: str
    scope: dict[str, Any]
    required_cited_domains: tuple[str, ...]
    terminal_policy: TerminalPolicy
    bounds: ManifestBounds
    usage_policy: UsagePolicy
    output_policy: OutputPolicy
    non_claims: tuple[str, ...]

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        encoded = value.encode("utf-8")
        if "\r" in value or not 1 <= len(encoded) <= 4096 or not value.strip():
            raise ValueError("manifest_query_invalid")
        return value

    @field_validator("required_cited_domains")
    @classmethod
    def validate_domains(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not 1 <= len(value) <= 8 or len(set(value)) != len(value):
            raise ValueError("manifest_domains_invalid")
        for domain in value:
            _validate_domain(domain)
        if value != ("docs.python.org", "peps.python.org"):
            raise ValueError("manifest_domains_invalid")
        return value

    @model_validator(mode="after")
    def validate_manifest_contract(self) -> "ManifestModel":
        scope_bytes = json.dumps(
            self.scope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        nodes, depth = _scope_shape(self.scope)
        if (
            len(scope_bytes) > self.bounds.scope_utf8_bytes_max
            or nodes > self.bounds.scope_nodes_max
            or depth > self.bounds.scope_depth_max
            or self.non_claims != NON_CLAIMS
        ):
            raise ValueError("manifest_invalid")
        return self


class CostObserved(StrictModel):
    status: Literal["observed"]
    amount: str
    currency: str
    pricing_basis: str
    estimate: Literal[True]

    @model_validator(mode="after")
    def validate_cost(self) -> "CostObserved":
        try:
            amount = Decimal(self.amount)
        except InvalidOperation as exc:
            raise ValueError("cost_invalid") from exc
        if (
            not _AMOUNT_RE.fullmatch(self.amount)
            or not amount.is_finite()
            or amount < 0
            or not _CURRENCY_RE.fullmatch(self.currency)
            or not _IDENTIFIER_RE.fullmatch(self.pricing_basis)
        ):
            raise ValueError("cost_invalid")
        return self


class CostNotObserved(StrictModel):
    status: Literal["not_observed"]


CostEstimate = Annotated[CostObserved | CostNotObserved, Field(discriminator="status")]


class ObservedUsage(StrictModel):
    status: Literal["observed"]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    call_count: int = Field(gt=0)
    cost_estimate: CostEstimate
    search_cost: CostEstimate

    @model_validator(mode="after")
    def validate_total(self) -> "ObservedUsage":
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("usage_total_invalid")
        if not isinstance(self.search_cost, CostNotObserved):
            raise ValueError("search_cost_invalid")
        return self


class UsageNotObserved(StrictModel):
    status: Literal["not_observed"]
    cost_estimate: CostNotObserved = CostNotObserved(status="not_observed")
    search_cost: CostNotObserved = CostNotObserved(status="not_observed")


UsageObservation = Annotated[
    ObservedUsage | UsageNotObserved,
    Field(discriminator="status"),
]


class SourceReceipt(StrictModel):
    repository_name: Literal["decision-research-agent"]
    service_name: Literal["decision-research-agent"]
    version: str
    source_commit: str
    source_tree: str
    archive_sha256: str
    manifest_sha256: str
    sanitized_compose_sha256: str
    backend_image_id: str
    docker_version: str = Field(min_length=1, max_length=128)
    compose_version: str = Field(min_length=1, max_length=128)
    source_clean: Literal[True]
    build_context: Literal["tracked_archive"]

    @model_validator(mode="after")
    def validate_source(self) -> "SourceReceipt":
        hashes = (
            self.archive_sha256,
            self.manifest_sha256,
            self.sanitized_compose_sha256,
        )
        if (
            not _VERSION_RE.fullmatch(self.version)
            or not _COMMIT_RE.fullmatch(self.source_commit)
            or not _COMMIT_RE.fullmatch(self.source_tree)
            or any(not _SHA256_RE.fullmatch(value) for value in hashes)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.backend_image_id)
        ):
            raise ValueError("source_receipt_invalid")
        return self


class ScenarioReceipt(StrictModel):
    scenario_id: Literal["cpython-313-free-threaded-pilot"]
    manifest_sha256: str
    request_sha256: str
    profile_id: Literal["generic"]
    required_cited_domains: list[str] = Field(min_length=1, max_length=8)
    provider_id: str
    primary_model_id: str
    fallback_model_id: str

    @model_validator(mode="after")
    def validate_scenario(self) -> "ScenarioReceipt":
        if (
            not _SHA256_RE.fullmatch(self.manifest_sha256)
            or not _SHA256_RE.fullmatch(self.request_sha256)
            or self.required_cited_domains != ["docs.python.org", "peps.python.org"]
            or any(
                not _IDENTIFIER_RE.fullmatch(value)
                for value in (
                    self.provider_id,
                    self.primary_model_id,
                    self.fallback_model_id,
                )
            )
        ):
            raise ValueError("scenario_receipt_invalid")
        return self


class LifecycleReceipt(StrictModel):
    docker_probe_ms: int = Field(ge=0, le=30_000)
    build_start_ms: int = Field(ge=0, le=1_200_000)
    research_ms: int = Field(ge=0, le=1_800_000)
    restart_replay_ms: int = Field(ge=0, le=300_000)
    active_ms: int = Field(ge=0, le=3_300_000)
    cleanup_ms: int = Field(ge=0, le=120_000)
    total_ms: int = Field(ge=0, le=3_450_000)
    loopback_binding_observed: Literal[True]
    health_identity_observed: Literal[True]

    @model_validator(mode="after")
    def validate_timing(self) -> "LifecycleReceipt":
        if (
            self.active_ms
            < self.build_start_ms + self.research_ms + self.restart_replay_ms
            or self.total_ms < self.docker_probe_ms + self.active_ms + self.cleanup_ms
        ):
            raise ValueError("lifecycle_timing_invalid")
        return self


class RunReceipt(StrictModel):
    run_id: str
    thread_id: str
    segment_id: str
    state_version: int = Field(ge=0)
    execution_status: Literal["completed"]
    review_status: Literal["not_required"]
    delivery_status: Literal["ready"]
    failure_cause: None
    profile_id: Literal["generic"]

    @model_validator(mode="after")
    def validate_ids(self) -> "RunReceipt":
        if any(
            not _IDENTIFIER_RE.fullmatch(value)
            for value in (self.run_id, self.thread_id, self.segment_id)
        ):
            raise ValueError("run_identity_invalid")
        return self


class ResultReceipt(StrictModel):
    artifact_id: Literal["research-report.md"]
    kind: Literal["research_report_markdown"]
    media_type: Literal["text/markdown"]
    utf8_bytes: int = Field(ge=1, le=1048576)
    sha256: str
    consumer_support: Literal["supported"]
    consumer_disposition: Literal["accept_draft"]

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("artifact_hash_invalid")
        return value


class EvidenceReceipt(StrictModel):
    evidence_id: str
    source_url: str
    source_identity: str
    retrieved_at: str
    citation_status: Literal["cited", "uncited"]
    verification_status: Literal["verified", "unverified"]

    @model_validator(mode="after")
    def validate_evidence(self) -> "EvidenceReceipt":
        if (
            not _IDENTIFIER_RE.fullmatch(self.evidence_id)
            or not self.source_identity.strip()
            or len(self.source_identity.encode("utf-8")) > 4096
            or len(self.retrieved_at.encode("utf-8")) > 64
        ):
            raise ValueError("evidence_invalid")
        try:
            timestamp = datetime.fromisoformat(self.retrieved_at)
            parsed = urlsplit(self.source_url)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("evidence_invalid") from exc
        hostname = parsed.hostname
        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
            or parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            raise ValueError("evidence_invalid")
        lowered = hostname.lower().rstrip(".")
        if lowered != hostname or lowered.endswith((".local", ".internal", ".localhost")):
            raise ValueError("evidence_invalid")
        try:
            address = ipaddress.ip_address(lowered)
        except ValueError:
            address = None
        if address is not None or not _DOMAIN_RE.fullmatch(lowered):
            raise ValueError("evidence_invalid")
        return self


class RestartReceipt(StrictModel):
    same_run_identity: Literal[True]
    same_thread_identity: Literal[True]
    same_segment_identity: Literal[True]
    state_version_non_regressing: Literal[True]
    same_terminal_state: Literal[True]
    same_evidence: Literal[True]
    same_artifact: Literal[True]
    same_consumer_disposition: Literal[True]


class ReplayReceipt(StrictModel):
    idempotent_replay: Literal[True]
    same_run_identity: Literal[True]
    same_thread_identity: Literal[True]
    same_segment_identity: Literal[True]
    unchanged_terminal_projection: Literal[True]


class CleanupReceipt(StrictModel):
    attempted: Literal[True]
    succeeded: Literal[True]
    zero_container_residue: Literal[True]
    zero_volume_residue: Literal[True]
    zero_network_residue: Literal[True]
    zero_temp_residue: Literal[True]


BOUNDARIES = {
    "producer_observation": "bounded",
    "downstream_business_acceptance": "not_claimed",
    "source_truth_or_independent_verification": "not_claimed",
    "exactly_once_execution_or_provider_side_effects": "not_claimed",
    "running_execution_recovery": "not_claimed",
    "multi_instance_high_availability": "not_claimed",
    "durable_usage_or_provider_billing": "not_claimed",
    "hosted_production_or_sla": "not_claimed",
}
LIMITS = (
    "A valid report is one bounded producer observation, not a downstream business decision.",
    "Recorded or cited Evidence is not independently verified source truth.",
    "Idempotent create reconciliation does not prove exactly-once execution or provider side effects.",
    "Client observation timeout does not cancel or recover a running server execution.",
    "Token and cost observations are process-local estimates, not durable usage or provider billing.",
    "The loopback Compose proof is not hosted production, multi-instance availability, or an SLA.",
)


class BoundariesModel(StrictModel):
    producer_observation: Literal["bounded"]
    downstream_business_acceptance: Literal["not_claimed"]
    source_truth_or_independent_verification: Literal["not_claimed"]
    exactly_once_execution_or_provider_side_effects: Literal["not_claimed"]
    running_execution_recovery: Literal["not_claimed"]
    multi_instance_high_availability: Literal["not_claimed"]
    durable_usage_or_provider_billing: Literal["not_claimed"]
    hosted_production_or_sla: Literal["not_claimed"]


class LiveReportModel(StrictModel):
    schema_version: Literal["dra.bounded-live-producer-evaluation.v1"]
    status: Literal["valid"]
    source: SourceReceipt
    scenario: ScenarioReceipt
    lifecycle: LifecycleReceipt
    run: RunReceipt
    result: ResultReceipt
    evidence: list[EvidenceReceipt] = Field(min_length=1, max_length=100)
    usage: UsageObservation
    restart: RestartReceipt
    replay: ReplayReceipt
    cleanup: CleanupReceipt
    boundaries: BoundariesModel
    limits: list[str]

    @model_validator(mode="after")
    def validate_report_contract(self) -> "LiveReportModel":
        if self.boundaries.model_dump(mode="python") != BOUNDARIES or self.limits != list(
            LIMITS
        ):
            raise ValueError("report_registry_invalid")
        ids = [row.evidence_id for row in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_duplicate")
        cited_hosts = {
            urlsplit(row.source_url).hostname
            for row in self.evidence
            if row.citation_status == "cited"
        }
        if any(domain not in cited_hosts for domain in self.scenario.required_cited_domains):
            raise ValueError("required_cited_domain_missing")
        if self.source.manifest_sha256 != self.scenario.manifest_sha256:
            raise ValueError("manifest_identity_drift")
        return self


class ErrorEnvelope(StrictModel):
    schema_version: Literal["dra.bounded-live-producer-evaluation-error.v1"]
    code: FailureCode
    phase: FailurePhase
    retryable: bool
    cleanup_status: CleanupStatus


def _assert_public_safe(value: Any) -> None:
    def visit(item: Any) -> None:
        if type(item) is dict:
            if any(key in _FORBIDDEN_PUBLIC_KEYS for key in item):
                _validation_fail("report_invalid")
            for key, nested in item.items():
                visit(key)
                visit(nested)
        elif type(item) is list:
            for nested in item:
                visit(nested)
        elif type(item) is str:
            if (
                _HOST_ABSOLUTE_PATH_RE.search(item)
                or _WINDOWS_ABSOLUTE_PATH_RE.search(item)
                or any(marker.lower() in item.lower() for marker in _FORBIDDEN_PUBLIC_MARKERS)
            ):
                _validation_fail("report_invalid")
        elif type(item) is float and (
            item != item or item in {float("inf"), float("-inf")}
        ):
            _validation_fail("report_invalid")

    visit(value)


def serialize_manifest(manifest: ManifestModel) -> bytes:
    try:
        validated = ManifestModel.model_validate(
            manifest.model_dump(mode="python"), strict=True
        )
    except ValidationError as exc:
        raise EvaluationValidationError("manifest_invalid") from exc
    return (
        json.dumps(
            validated.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _bounded_regular_read(path: Path, *, maximum: int, code: str) -> bytes:
    descriptor = -1
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            _validation_fail(code)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size > maximum
        ):
            _validation_fail(code)
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            _validation_fail(code)
        after = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            _validation_fail(code)
        return raw
    except EvaluationValidationError:
        raise
    except OSError as exc:
        raise EvaluationValidationError(code) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_manifest(path: Path) -> ManifestModel:
    raw = _bounded_regular_read(path, maximum=MAX_MANIFEST_BYTES, code="manifest_invalid")
    try:
        manifest = ManifestModel.model_validate_json(raw, strict=True)
    except (ValidationError, UnicodeError, ValueError) as exc:
        raise EvaluationValidationError("manifest_invalid") from exc
    if serialize_manifest(manifest) != raw:
        _validation_fail("manifest_invalid")
    return manifest


def _validation_code(payload: Any) -> str:
    if type(payload) is dict:
        if "usage" in payload:
            try:
                usage = payload["usage"]
                if type(usage) is dict:
                    ObservedUsage.model_validate(usage, strict=True) if usage.get(
                        "status"
                    ) == "observed" else UsageNotObserved.model_validate(
                        usage, strict=True
                    )
            except ValidationError:
                return "usage_invalid"
        if "evidence" in payload:
            try:
                rows = payload["evidence"]
                if type(rows) is not list:
                    return "evidence_invalid"
                for row in rows:
                    EvidenceReceipt.model_validate(row, strict=True)
            except ValidationError:
                return "evidence_invalid"
    return "report_invalid"


def validate_live_report(payload: Any) -> LiveReportModel:
    try:
        model = LiveReportModel.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise EvaluationValidationError(_validation_code(payload)) from exc
    canonical = model.model_dump(mode="json")
    _assert_public_safe(canonical)
    try:
        serialized = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvaluationValidationError("report_invalid") from exc
    if len(serialized) + 1 > MAX_PUBLIC_BYTES:
        _validation_fail("report_invalid")
    return model


def serialize_report(report: LiveReportModel | dict[str, Any]) -> bytes:
    payload = report.model_dump(mode="python") if isinstance(report, LiveReportModel) else report
    model = validate_live_report(payload)
    raw = (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(raw) > MAX_PUBLIC_BYTES:
        _validation_fail("report_invalid")
    return raw


def render_markdown(report: LiveReportModel | dict[str, Any]) -> str:
    payload = report.model_dump(mode="python") if isinstance(report, LiveReportModel) else report
    model = validate_live_report(payload)
    lines = [
        "# Bounded Live Producer Evaluation v1",
        "",
        "Status: valid bounded producer observation.",
        "",
        "## Source Receipt",
        "",
        f"- Repository: `{model.source.repository_name}`",
        f"- Version: `{model.source.version}`",
        f"- Source commit: `{model.source.source_commit}`",
        f"- Source tree: `{model.source.source_tree}`",
        f"- Tracked archive SHA-256: `{model.source.archive_sha256}`",
        f"- Manifest SHA-256: `{model.source.manifest_sha256}`",
        "- Build context: `tracked_archive`",
        "",
        "## Scenario And Result",
        "",
        f"- Scenario: `{model.scenario.scenario_id}`",
        f"- Run: `{model.run.run_id}`",
        f"- Artifact: `{model.result.artifact_id}` (`{model.result.sha256}`)",
        f"- Consumer projection: `{model.result.consumer_support} / {model.result.consumer_disposition}`",
        "",
        "## Evidence",
        "",
    ]
    for row in model.evidence:
        lines.append(
            f"- `{row.evidence_id}` — {row.source_url} — `{row.citation_status}` / `{row.verification_status}`"
        )
    lines.extend(["", "## Boundaries", ""])
    for key, value in BOUNDARIES.items():
        lines.append(f"- `{key}: {value}`")
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {value}" for value in LIMITS)
    rendered = "\n".join(lines) + "\n"
    if len(rendered.encode("utf-8")) > MAX_PUBLIC_BYTES:
        _validation_fail("report_invalid")
    _assert_public_safe({"rendered_markdown": rendered})
    return rendered


def serialize_error(error: EvaluationError) -> bytes:
    envelope = ErrorEnvelope(
        schema_version=ERROR_SCHEMA_VERSION,
        code=error.code,
        phase=error.phase,
        retryable=error.retryable,
        cleanup_status=error.cleanup_status,
    )
    return (
        json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
