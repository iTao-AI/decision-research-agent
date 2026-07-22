"""Bounded producer orchestration, projection, and stable CLI boundary."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence, TypeVar
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from pydantic import ValidationError

from api.run_creation_models import run_create_request_hash
from api.run_failure_cause_models import (
    ObservedRunFailureCause,
    RunFailureCauseProjectionAdapter,
)
from scripts.bounded_live_producer_contracts import (
    BOUNDARIES,
    LIMITS,
    MANIFEST_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    CleanupReceipt,
    CleanupStatus,
    CostNotObserved,
    EvaluationError,
    EvaluationValidationError,
    EvidenceReceipt,
    FAILURE_REGISTRY,
    FailureCode,
    FailurePhase,
    LiveReportModel,
    ObservedUsage,
    ReplayReceipt,
    ResultBoundaryDiagnostic,
    ResultDiagnosticReason,
    ResultDiagnosticStage,
    RunFailureDiagnostic,
    RestartReceipt,
    ResultReceipt,
    RunReceipt,
    UsageNotObserved,
    load_manifest,
    render_markdown,
    serialize_error,
    serialize_manifest,
    serialize_report,
)
from scripts.bounded_live_producer_diagnostics import (
    DiagnosticOutputError,
    DiagnosticSink,
    preflight_diagnostic_dir,
    publish_result_diagnostic,
)
from scripts.bounded_live_producer_http import CreateAmbiguous, ProofHttpClient
from scripts.downstream_consumer_contract import (
    ContractValidationError,
    project_consumer_case,
)


MANIFEST_PATH = (
    PROJECT_ROOT / "benchmarks" / "bounded-live-producer-v1" / "manifest.json"
)
JSON_OUTPUT = Path("docs/evidence/bounded-live-producer-v1.json")
MARKDOWN_OUTPUT = Path("docs/evidence/bounded-live-producer-v1.md")
_ACK_KEYS = {
    "status",
    "run_id",
    "thread_id",
    "segment_id",
    "idempotent_replay",
}
_USAGE_KEYS = {
    "total_prompt",
    "total_completion",
    "total_tokens",
    "total_cost",
    "call_count",
}
_IDENTIFIER_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
)
_DOCKER_ID_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DOCKER_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)


def _error(
    code: FailureCode | str,
    phase: FailurePhase | str,
    *,
    diagnostic: ResultBoundaryDiagnostic | RunFailureDiagnostic | None = None,
) -> EvaluationError:
    return EvaluationError(code, phase, False, diagnostic=diagnostic)


def _consumer_diagnostic(
    reason: ResultDiagnosticReason,
    *,
    response_bytes: int,
) -> ResultBoundaryDiagnostic:
    return ResultBoundaryDiagnostic(
        stage=ResultDiagnosticStage.CONSUMER_CONTRACT,
        reason=reason,
        http_status=200,
        response_bytes=response_bytes,
    )


def _identifier(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 128
        and value[0].isalnum()
        and value.isascii()
        and all(character in _IDENTIFIER_CHARS for character in value)
    )


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _error(FailureCode.REPORT_INVALID, FailurePhase.OUTPUT) from exc


@dataclass(frozen=True, slots=True)
class TerminalSnapshot:
    """Bounded terminal comparison facts; raw content is deliberately absent."""

    run: RunReceipt
    result: ResultReceipt
    evidence: tuple[EvidenceReceipt, ...]
    terminal_state: tuple[str, str, str]
    state_version: int
    consumer_support: str
    consumer_disposition: str

    def evidence_projection(self) -> tuple[bytes, ...]:
        return tuple(
            _canonical_bytes(row.model_dump(mode="json")) for row in self.evidence
        )

    def artifact_projection(self) -> tuple[object, ...]:
        return (
            self.result.artifact_id,
            self.result.kind,
            self.result.media_type,
            self.result.utf8_bytes,
            self.result.sha256,
        )


def run_provider_free_check(*, manifest_path: Path = MANIFEST_PATH) -> dict[str, str]:
    """Validate fixed registries and deterministic serializers without I/O services."""

    manifest = load_manifest(manifest_path)
    if serialize_manifest(manifest) != manifest_path.read_bytes():
        raise _error(FailureCode.MANIFEST_INVALID, FailurePhase.INPUT)
    registered = frozenset(code for codes in FAILURE_REGISTRY.values() for code in codes)
    if registered != frozenset(FailureCode) or set(FAILURE_REGISTRY) != set(FailurePhase):
        raise _error(FailureCode.MANIFEST_INVALID, FailurePhase.INPUT)
    if BOUNDARIES["producer_observation"] != "bounded" or len(LIMITS) != 6:
        raise _error(FailureCode.MANIFEST_INVALID, FailurePhase.INPUT)
    return {
        "mode": "provider_free",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "valid",
    }


def _request_thread_id(request_bytes: bytes) -> str:
    try:
        payload = json.loads(request_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _error(FailureCode.CREATE_RESPONSE_INVALID, FailurePhase.CREATE) from exc
    if type(payload) is not dict or not _identifier(payload.get("thread_id")):
        raise _error(FailureCode.CREATE_RESPONSE_INVALID, FailurePhase.CREATE)
    return payload["thread_id"]


def _require_create_identity(
    acknowledgement: object,
    *,
    thread_id: str,
    replay: bool,
) -> dict[str, Any]:
    if type(acknowledgement) is not dict or set(acknowledgement) != _ACK_KEYS:
        raise _error(FailureCode.CREATE_RESPONSE_INVALID, FailurePhase.CREATE)
    if (
        acknowledgement.get("status") != "started"
        or type(acknowledgement.get("idempotent_replay")) is not bool
        or acknowledgement["idempotent_replay"] is not replay
    ):
        raise _error(FailureCode.CREATE_RESPONSE_INVALID, FailurePhase.CREATE)
    if acknowledgement.get("thread_id") != thread_id:
        raise _error(FailureCode.CREATE_IDENTITY_MISMATCH, FailurePhase.CREATE)
    if not _identifier(acknowledgement.get("run_id")) or not _identifier(
        acknowledgement.get("segment_id")
    ):
        raise _error(FailureCode.CREATE_IDENTITY_MISMATCH, FailurePhase.CREATE)
    return acknowledgement


def reconcile_create(
    client: Any,
    *,
    request_bytes: bytes,
    key: str,
) -> dict[str, Any]:
    """Allow one exact replay only after an ambiguous keyed acknowledgement."""

    thread_id = _request_thread_id(request_bytes)
    try:
        accepted = client.create(request_bytes=request_bytes, idempotency_key=key)
    except CreateAmbiguous:
        try:
            replayed = client.create(request_bytes=request_bytes, idempotency_key=key)
        except CreateAmbiguous as exc:
            raise _error(
                FailureCode.CREATE_RECONCILIATION_UNRESOLVED,
                FailurePhase.CREATE,
            ) from exc
        return _require_create_identity(replayed, thread_id=thread_id, replay=True)
    return _require_create_identity(accepted, thread_id=thread_id, replay=False)


def _run_failure_diagnostic(value: object) -> RunFailureDiagnostic:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        cause = RunFailureCauseProjectionAdapter.validate_json(raw, strict=True)
    except (TypeError, ValueError, ValidationError):
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE) from None
    if type(cause) is not ObservedRunFailureCause:
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    return RunFailureDiagnostic(
        cause_schema_version=cause.schema_version,
        observation_status=cause.observation_status,
        phase=cause.phase,
        code=cause.code,
    )


def _terminal_error(status: Mapping[str, Any]) -> EvaluationError | None:
    execution = status.get("execution_status")
    delivery = status.get("delivery_status")
    if execution == "failed":
        return _error(
            FailureCode.RUN_FAILED,
            FailurePhase.OBSERVE,
            diagnostic=_run_failure_diagnostic(status.get("failure_cause")),
        )
    if status.get("failure_cause") is not None:
        return _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    if execution == "completed_with_fallback":
        return _error(FailureCode.RUN_FALLBACK_REJECTED, FailurePhase.OBSERVE)
    if execution == "completed" and delivery != "ready":
        return _error(FailureCode.RUN_DELIVERY_NOT_READY, FailurePhase.OBSERVE)
    if execution == "completed" and delivery == "ready":
        return None
    return _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)


def _validate_artifact_hash(result_payload: object) -> None:
    if type(result_payload) is not dict or type(result_payload.get("artifact")) is not dict:
        return
    artifact = result_payload["artifact"]
    content = artifact.get("content")
    content_hash = artifact.get("content_hash")
    if type(content) is str and type(content_hash) is str:
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash:
            raise _error(FailureCode.ARTIFACT_HASH_MISMATCH, FailurePhase.RESULT)


def project_live_observation(
    *,
    status_payload: dict[str, Any],
    result_payload: dict[str, Any],
    result_response_bytes: int,
    expected_run_id: str,
    expected_thread_id: str,
    expected_segment_id: str,
    required_cited_domains: Sequence[str],
) -> TerminalSnapshot:
    """Project one accepted terminal response into bounded comparison facts."""

    if type(status_payload) is not dict:
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    if (
        status_payload.get("run_id") != expected_run_id
        or status_payload.get("thread_id") != expected_thread_id
        or status_payload.get("profile_id") != "generic"
    ):
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    terminal_error = _terminal_error(status_payload)
    if terminal_error is not None:
        raise terminal_error
    if (
        status_payload.get("execution_status") != "completed"
        or status_payload.get("review_status") != "not_required"
        or status_payload.get("delivery_status") != "ready"
        or status_payload.get("failure_cause") is not None
        or type(status_payload.get("state_version")) is not int
        or status_payload["state_version"] < 0
    ):
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    segments = status_payload.get("segments")
    if type(segments) is not list or len(segments) != 1 or type(segments[0]) is not dict:
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
    segment = segments[0]
    if (
        segment.get("segment_id") != expected_segment_id
        or segment.get("run_id") != expected_run_id
        or segment.get("kind") != "initial"
        or segment.get("sequence") != 0
        or segment.get("attempt") != 1
        or segment.get("status") != "completed"
    ):
        raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)

    raw_evidence = status_payload.get("evidence")
    if type(raw_evidence) is not list or not raw_evidence:
        raise _error(FailureCode.EVIDENCE_MISSING, FailurePhase.EVIDENCE)
    if len(raw_evidence) > 100:
        raise _error(FailureCode.EVIDENCE_INVALID, FailurePhase.EVIDENCE)
    if any(
        type(row) is not dict
        or row.get("run_id") != expected_run_id
        or row.get("segment_id") != expected_segment_id
        for row in raw_evidence
    ):
        raise _error(FailureCode.EVIDENCE_INVALID, FailurePhase.EVIDENCE)
    _validate_artifact_hash(result_payload)
    try:
        projection = project_consumer_case(
            case_id="bounded-live-producer-v1",
            status_payload=status_payload,
            result_http_status=200,
            result_payload=result_payload,
        )
    except ContractValidationError as exc:
        if exc.code == "contract_evidence_invalid":
            raise _error(FailureCode.EVIDENCE_INVALID, FailurePhase.EVIDENCE) from exc
        if exc.code == "contract_artifact_invalid":
            raise _error(FailureCode.ARTIFACT_INVALID, FailurePhase.RESULT) from exc
        if exc.code == "contract_state_invalid":
            raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE) from exc
        if exc.code == "contract_result_invalid":
            raise _error(
                FailureCode.CONSUMER_PROJECTION_INVALID,
                FailurePhase.RESULT,
                diagnostic=_consumer_diagnostic(
                    ResultDiagnosticReason.CONTRACT_RESULT_INVALID,
                    response_bytes=result_response_bytes,
                ),
            ) from exc
        if exc.code == "contract_schema_invalid":
            raise _error(
                FailureCode.CONSUMER_PROJECTION_INVALID,
                FailurePhase.RESULT,
                diagnostic=_consumer_diagnostic(
                    ResultDiagnosticReason.CONTRACT_SCHEMA_INVALID,
                    response_bytes=result_response_bytes,
                ),
            ) from exc
        raise _error(
            FailureCode.CONSUMER_PROJECTION_INVALID,
            FailurePhase.RESULT,
        ) from exc
    expected = projection.get("expected")
    if expected == {"support": "partial", "disposition": "block_fallback"}:
        raise _error(FailureCode.RUN_FALLBACK_REJECTED, FailurePhase.RESULT)
    if expected != {"support": "supported", "disposition": "accept_draft"}:
        raise _error(
            FailureCode.CONSUMER_PROJECTION_INVALID,
            FailurePhase.RESULT,
            diagnostic=ResultBoundaryDiagnostic(
                stage=ResultDiagnosticStage.PROJECTION_DISPOSITION,
                reason=ResultDiagnosticReason.PROJECTION_DISPOSITION_INVALID,
                http_status=200,
                response_bytes=result_response_bytes,
            ),
        )
    try:
        evidence = tuple(
            EvidenceReceipt.model_validate(row, strict=True)
            for row in projection["evidence"]
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise _error(FailureCode.EVIDENCE_INVALID, FailurePhase.EVIDENCE) from exc
    cited_hosts = {
        urlsplit(row.source_url).hostname
        for row in evidence
        if row.citation_status == "cited"
    }
    if any(domain not in cited_hosts for domain in required_cited_domains):
        raise _error(
            FailureCode.REQUIRED_CITED_DOMAIN_MISSING,
            FailurePhase.EVIDENCE,
        )
    artifact = result_payload["artifact"]
    content = artifact["content"]
    try:
        run = RunReceipt(
            run_id=expected_run_id,
            thread_id=expected_thread_id,
            segment_id=expected_segment_id,
            state_version=status_payload["state_version"],
            execution_status="completed",
            review_status="not_required",
            delivery_status="ready",
            failure_cause=None,
            profile_id="generic",
        )
        result = ResultReceipt(
            artifact_id=artifact["artifact_id"],
            kind=artifact["kind"],
            media_type=artifact["media_type"],
            utf8_bytes=len(content.encode("utf-8")),
            sha256=artifact["content_hash"],
            consumer_support="supported",
            consumer_disposition="accept_draft",
        )
    except (KeyError, TypeError, UnicodeError, ValidationError) as exc:
        raise _error(FailureCode.ARTIFACT_INVALID, FailurePhase.RESULT) from exc
    return TerminalSnapshot(
        run=run,
        result=result,
        evidence=evidence,
        terminal_state=("completed", "not_required", "ready"),
        state_version=status_payload["state_version"],
        consumer_support="supported",
        consumer_disposition="accept_draft",
    )


def observe_usage(
    payload: object | None,
    *,
    primary_model_id: str,
    fallback_model_id: str,
    pricing_basis: str | None = None,
    currency: str | None = None,
    pricing_identity_matches: bool = False,
) -> ObservedUsage | UsageNotObserved:
    """Validate one process-local usage summary and project estimate metadata."""

    if payload is None:
        return UsageNotObserved(status="not_observed")
    if type(payload) is not dict or set(payload) != _USAGE_KEYS:
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
    integers = ("total_prompt", "total_completion", "total_tokens", "call_count")
    if any(type(payload[key]) is not int or payload[key] < 0 for key in integers):
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
    if payload["total_prompt"] + payload["total_completion"] != payload["total_tokens"]:
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
    cost = payload["total_cost"]
    if type(cost) not in {int, float} or not math.isfinite(cost) or cost < 0:
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
    if payload["call_count"] == 0:
        if any(payload[key] != 0 for key in integers[:-1]) or cost != 0:
            raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
        return UsageNotObserved(status="not_observed")
    if payload["total_tokens"] <= 0:
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE)
    cost_estimate = CostNotObserved(status="not_observed")
    try:
        return ObservedUsage(
            status="observed",
            prompt_tokens=payload["total_prompt"],
            completion_tokens=payload["total_completion"],
            total_tokens=payload["total_tokens"],
            call_count=payload["call_count"],
            cost_estimate=cost_estimate,
            search_cost=CostNotObserved(status="not_observed"),
        )
    except ValidationError as exc:
        raise _error(FailureCode.USAGE_INVALID, FailurePhase.USAGE) from exc


def compare_restart(before: TerminalSnapshot, after: TerminalSnapshot) -> RestartReceipt:
    """Compare only bounded public facts captured before and after restart."""

    if (
        before.run.run_id != after.run.run_id
        or before.run.thread_id != after.run.thread_id
        or before.run.segment_id != after.run.segment_id
        or after.state_version < before.state_version
        or before.terminal_state != after.terminal_state
    ):
        raise _error(FailureCode.RESTART_IDENTITY_DRIFT, FailurePhase.RESTART)
    if before.evidence_projection() != after.evidence_projection():
        raise _error(FailureCode.RESTART_EVIDENCE_DRIFT, FailurePhase.RESTART)
    if before.artifact_projection() != after.artifact_projection():
        raise _error(FailureCode.RESTART_ARTIFACT_DRIFT, FailurePhase.RESTART)
    if (
        before.consumer_support,
        before.consumer_disposition,
    ) != (after.consumer_support, after.consumer_disposition):
        raise _error(FailureCode.RESTART_ARTIFACT_DRIFT, FailurePhase.RESTART)
    return RestartReceipt(
        same_run_identity=True,
        same_thread_identity=True,
        same_segment_identity=True,
        state_version_non_regressing=True,
        same_terminal_state=True,
        same_evidence=True,
        same_artifact=True,
        same_consumer_disposition=True,
    )


def validate_replay(
    acknowledgement: object,
    *,
    before: TerminalSnapshot,
    after: TerminalSnapshot,
) -> ReplayReceipt:
    """Require exact same-key replay acknowledgement and unchanged terminal facts."""

    if type(acknowledgement) is not dict or set(acknowledgement) != _ACK_KEYS:
        raise _error(FailureCode.IDEMPOTENT_REPLAY_INVALID, FailurePhase.REPLAY)
    if acknowledgement.get("run_id") != before.run.run_id:
        raise _error(FailureCode.DUPLICATE_RUN_OBSERVED, FailurePhase.REPLAY)
    if (
        acknowledgement.get("status") != "started"
        or acknowledgement.get("thread_id") != before.run.thread_id
        or acknowledgement.get("segment_id") != before.run.segment_id
        or acknowledgement.get("idempotent_replay") is not True
    ):
        raise _error(FailureCode.IDEMPOTENT_REPLAY_INVALID, FailurePhase.REPLAY)
    unchanged = (
        before.run == after.run
        and before.terminal_state == after.terminal_state
        and before.evidence_projection() == after.evidence_projection()
        and before.artifact_projection() == after.artifact_projection()
        and before.consumer_support == after.consumer_support
        and before.consumer_disposition == after.consumer_disposition
    )
    if not unchanged:
        raise _error(FailureCode.IDEMPOTENT_REPLAY_INVALID, FailurePhase.REPLAY)
    return ReplayReceipt(
        idempotent_replay=True,
        same_run_identity=True,
        same_thread_identity=True,
        same_segment_identity=True,
        unchanged_terminal_projection=True,
    )


T = TypeVar("T")


def run_cleanup_guarded(
    primary: Callable[[], T],
    cleanup: Callable[[], CleanupReceipt],
) -> tuple[T, CleanupReceipt]:
    """Always run cleanup and retain typed primary plus cleanup failures locally."""

    primary_result: T | None = None
    primary_error: BaseException | None = None
    try:
        primary_result = primary()
    except BaseException as exc:
        primary_error = exc
    try:
        cleanup_result = cleanup()
    except BaseException as raw_cleanup_error:
        cleanup_error = (
            raw_cleanup_error
            if isinstance(raw_cleanup_error, EvaluationError)
            and raw_cleanup_error.phase is FailurePhase.CLEANUP
            else EvaluationError(
                FailureCode.CLEANUP_FAILED,
                FailurePhase.CLEANUP,
                False,
                CleanupStatus.FAILED,
            )
        )
        if primary_error is not None:
            raise BaseExceptionGroup(
                "bounded producer primary and cleanup failures",
                [primary_error, cleanup_error],
            )
        raise cleanup_error from raw_cleanup_error
    if primary_error is not None:
        if isinstance(primary_error, EvaluationError):
            raise EvaluationError(
                primary_error.code,
                primary_error.phase,
                primary_error.retryable,
                CleanupStatus.SUCCEEDED,
                diagnostic=primary_error.diagnostic,
            ) from primary_error
        raise EvaluationError(
            FailureCode.EVALUATION_INTERNAL_ERROR,
            FailurePhase.INTERNAL,
            False,
            CleanupStatus.SUCCEEDED,
        ) from primary_error
    return primary_result, cleanup_result  # type: ignore[return-value]


def _cleanup_pre_guard_task_temp(
    task_temp_parent: Path,
    *,
    remaining_seconds: Callable[[float], float],
) -> CleanupReceipt:
    """Remove only the exact task temp created before project cleanup takes ownership."""

    resolved = task_temp_parent.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if (
        resolved.parent != temp_root
        or re.fullmatch(r"dra-bounded-producer-[0-9a-f]{32}", resolved.name) is None
    ):
        raise EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        )
    remaining_seconds(1.0)
    try:
        shutil.rmtree(resolved)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        ) from exc
    remaining_seconds(1.0)
    if resolved.exists():
        raise EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        )
    return CleanupReceipt(
        attempted=True,
        succeeded=True,
        zero_container_residue=True,
        zero_volume_residue=True,
        zero_network_residue=True,
        zero_temp_residue=True,
    )


def _output_directory(repository_root: Path) -> tuple[Path, int]:
    try:
        root = repository_root.resolve(strict=True)
        for candidate in (root, root / "docs", root / "docs" / "evidence"):
            metadata = candidate.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise ValueError
        directory = root / "docs" / "evidence"
        descriptor = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        after = directory.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
        ):
            os.close(descriptor)
            raise ValueError
        return root, descriptor
    except (OSError, ValueError) as exc:
        raise _error(FailureCode.OUTPUT_INVALID, FailurePhase.INPUT) from exc


def _write_at(descriptor: int, name: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(name, flags, 0o600, dir_fd=descriptor)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(file_descriptor, view)
            if written <= 0:
                raise OSError
            view = view[written:]
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


def publish_paired_output(
    repository_root: Path,
    report: LiveReportModel | dict[str, Any],
    *,
    remaining_seconds: Callable[[float], float] | None = None,
) -> tuple[Path, Path]:
    """Publish the fixed JSON/Markdown pair without exposing partial JSON authority."""

    if remaining_seconds is not None:
        remaining_seconds(1.0)
    try:
        json_payload = serialize_report(report)
        if serialize_report(report) != json_payload:
            raise ValueError
        markdown_payload = render_markdown(report).encode("utf-8")
    except (EvaluationValidationError, ValidationError, TypeError, ValueError) as exc:
        raise _error(FailureCode.REPORT_INVALID, FailurePhase.OUTPUT) from exc
    if remaining_seconds is not None:
        remaining_seconds(1.0)
    root, directory_descriptor = _output_directory(repository_root)
    target_names = (JSON_OUTPUT.name, MARKDOWN_OUTPUT.name)
    temporary_names = tuple(
        f".bounded-live-producer-{secrets.token_hex(16)}.tmp" for _ in target_names
    )
    published: list[str] = []
    committed = False
    primary_error: EvaluationError | None = None
    try:
        for target in target_names:
            if remaining_seconds is not None:
                remaining_seconds(1.0)
            try:
                os.stat(target, dir_fd=directory_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise _error(FailureCode.OUTPUT_EXISTS, FailurePhase.OUTPUT)
        _write_at(directory_descriptor, temporary_names[0], json_payload)
        if remaining_seconds is not None:
            remaining_seconds(1.0)
        _write_at(directory_descriptor, temporary_names[1], markdown_payload)
        for index in (1, 0):
            if remaining_seconds is not None:
                remaining_seconds(1.0)
            temporary = temporary_names[index]
            target = target_names[index]
            os.link(
                temporary,
                target,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            published.append(target)
        for temporary in temporary_names:
            os.unlink(temporary, dir_fd=directory_descriptor)
        if remaining_seconds is not None:
            remaining_seconds(1.0)
        os.fsync(directory_descriptor)
        if remaining_seconds is not None:
            remaining_seconds(1.0)
        committed = True
    except EvaluationError as exc:
        primary_error = exc
    except OSError as exc:
        primary_error = _error(FailureCode.OUTPUT_WRITE_FAILED, FailurePhase.OUTPUT)
        primary_error.__cause__ = exc
    finally:
        if not committed:
            for target in reversed(published):
                try:
                    os.unlink(target, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    continue
                except OSError:
                    rollback_name = (
                        f".bounded-live-producer-{secrets.token_hex(16)}.rollback"
                    )
                    try:
                        os.rename(
                            target,
                            rollback_name,
                            src_dir_fd=directory_descriptor,
                            dst_dir_fd=directory_descriptor,
                        )
                    except OSError:
                        continue
                    try:
                        os.unlink(rollback_name, dir_fd=directory_descriptor)
                    except OSError:
                        pass
        for temporary in temporary_names:
            try:
                os.unlink(temporary, dir_fd=directory_descriptor)
            except OSError:
                pass
        if not committed:
            try:
                os.fsync(directory_descriptor)
            except OSError:
                pass
        try:
            os.close(directory_descriptor)
        except OSError:
            pass
    if primary_error is not None:
        raise primary_error
    return root / JSON_OUTPUT, root / MARKDOWN_OUTPUT


def _new_request(manifest: Any) -> tuple[bytes, str, str, str]:
    thread_id = f"proof-thread-{secrets.token_hex(16)}"
    key = f"proof-key-{secrets.token_hex(16)}"
    payload = {
        "query": manifest.query,
        "thread_id": thread_id,
        "profile_id": manifest.profile_id,
        "scope": manifest.scope,
    }
    request_bytes = _canonical_bytes(payload)
    request_hash = run_create_request_hash(
        query=manifest.query,
        thread_id=thread_id,
        profile_id=manifest.profile_id,
        scope=manifest.scope,
    )
    return request_bytes, request_hash, thread_id, key


def observe_terminal(
    client: ProofHttpClient,
    *,
    accepted: Mapping[str, Any],
    required_cited_domains: Sequence[str],
    remaining_seconds: Callable[[float], float],
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[TerminalSnapshot, dict[str, Any], dict[str, Any]]:
    """Poll one accepted run without cancellation or a fresh retry budget."""

    run_id = accepted.get("run_id")
    thread_id = accepted.get("thread_id")
    segment_id = accepted.get("segment_id")
    if not all(_identifier(value) for value in (run_id, thread_id, segment_id)):
        raise _error(FailureCode.CREATE_IDENTITY_MISMATCH, FailurePhase.CREATE)
    while True:
        remaining_seconds(30.0)
        status = client.status(run_id=run_id, timeout_seconds=30.0)
        if (
            type(status) is not dict
            or status.get("run_id") != run_id
            or status.get("thread_id") != thread_id
            or status.get("profile_id") != "generic"
        ):
            raise _error(FailureCode.RUN_STATE_INVALID, FailurePhase.OBSERVE)
        execution = status.get("execution_status")
        if execution in {"pending", "running"}:
            delay = remaining_seconds(1.0)
            sleep(delay)
            continue
        terminal_error = _terminal_error(status)
        if terminal_error is not None:
            raise terminal_error
        result_observation = client.result_observation(
            run_id=run_id,
            timeout_seconds=30.0,
        )
        result = result_observation.body
        projected = project_live_observation(
            status_payload=status,
            result_payload=result,
            result_response_bytes=result_observation.response_bytes,
            expected_run_id=run_id,
            expected_thread_id=thread_id,
            expected_segment_id=segment_id,
            required_cited_domains=required_cited_domains,
        )
        return projected, status, result


_DOCKER_PROCESS_ENV = (
    "PATH",
    "HOME",
    "TMPDIR",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "XDG_CONFIG_HOME",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "PYTHON_DOTENV_DISABLED",
)


def _scrubbed_docker_environment() -> dict[str, str]:
    environment = {
        key: os.environ[key] for key in _DOCKER_PROCESS_ENV if key in os.environ
    }
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    return environment


def _preflight_output_paths(repository_root: Path) -> None:
    _root, descriptor = _output_directory(repository_root)
    try:
        for name in (JSON_OUTPUT.name, MARKDOWN_OUTPUT.name):
            try:
                os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise _error(FailureCode.OUTPUT_EXISTS, FailurePhase.OUTPUT)
    finally:
        os.close(descriptor)


def _bounded_public_version(value: str, *, code: FailureCode) -> str:
    stripped = value.strip()
    if not stripped or len(stripped.encode("utf-8")) > 128 or "\n" in stripped:
        raise _error(code, FailurePhase.DOCKER)
    return stripped


def _project_result(
    project: Any,
    arguments: Sequence[str],
    deadline: Any,
    *,
    compose: bool = False,
) -> str:
    result = project._invoke(arguments, deadline, compose=compose)
    if type(result.stdout) is not str:
        raise _error(deadline.code, deadline.phase)
    return result.stdout.strip()


def _project_resource_ids(project: Any, deadline: Any) -> None:
    containers = tuple(
        value
        for value in _project_result(
            project,
            (
                "docker",
                "container",
                "ls",
                "-a",
                "-q",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project.project_name}",
            ),
            deadline,
        ).splitlines()
        if value
    )
    volumes = tuple(
        value
        for value in _project_result(
            project,
            (
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={project.project_name}",
            ),
            deadline,
        ).splitlines()
        if value
    )
    networks = tuple(
        value
        for value in _project_result(
            project,
            (
                "docker",
                "network",
                "ls",
                "-q",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project.project_name}",
            ),
            deadline,
        ).splitlines()
        if value
    )
    if (
        any(_DOCKER_ID_RE.fullmatch(value) is None for value in containers)
        or any(
            _DOCKER_NAME_RE.fullmatch(value) is None
            or not value.startswith(f"{project.project_name}_")
            for value in volumes
        )
        or any(_DOCKER_ID_RE.fullmatch(value) is None for value in networks)
    ):
        raise _error(FailureCode.SERVICE_IDENTITY_INVALID, FailurePhase.DOCKER)
    project.merge_resource_ownership(
        container_ids=containers,
        volume_ids=volumes,
        network_ids=networks,
    )


def _compose_service_container(project: Any, service: str, deadline: Any) -> str:
    values = _project_result(
        project,
        ("ps", "-q", service),
        deadline,
        compose=True,
    ).splitlines()
    if len(values) != 1 or _DOCKER_ID_RE.fullmatch(values[0]) is None:
        raise _error(FailureCode.SERVICE_IDENTITY_INVALID, FailurePhase.DOCKER)
    return values[0]


def _loopback_port(project: Any, service: str, target: int, deadline: Any) -> int:
    container_id = _compose_service_container(project, service, deadline)
    raw = _project_result(
        project,
        (
            "docker",
            "inspect",
            "--format",
            "{{json .NetworkSettings.Ports}}",
            container_id,
        ),
        deadline,
    )
    try:
        ports = json.loads(raw)
        bindings = ports[f"{target}/tcp"]
        binding = bindings[0]
        host_port_value = binding["HostPort"]
        if (
            type(host_port_value) is not str
            or not host_port_value.isascii()
            or not host_port_value.isdigit()
        ):
            raise ValueError
        host_port = int(host_port_value)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _error(FailureCode.SERVICE_IDENTITY_INVALID, FailurePhase.DOCKER) from exc
    if (
        type(ports) is not dict
        or type(bindings) is not list
        or len(bindings) != 1
        or type(binding) is not dict
        or set(binding) != {"HostIp", "HostPort"}
        or binding["HostIp"] != "127.0.0.1"
        or not 1 <= host_port <= 65535
    ):
        raise _error(FailureCode.SERVICE_IDENTITY_INVALID, FailurePhase.DOCKER)
    return host_port


def _wait_for_health(
    client: ProofHttpClient,
    *,
    remaining_seconds: Callable[[float], float],
) -> None:
    while True:
        try:
            client.health(timeout_seconds=30.0)
            return
        except EvaluationError as exc:
            if exc.code is not FailureCode.SERVICE_IDENTITY_INVALID:
                raise
        time.sleep(remaining_seconds(1.0))


def restart_backend_transport(
    project: Any,
    *,
    api_key: str,
    deadline: Any,
) -> ProofHttpClient:
    """Restart backend and bind a fresh client to its current loopback port."""

    project.restart_backend(deadline)
    backend_port = _loopback_port(project, "backend", 8000, deadline)
    client = ProofHttpClient(
        port=backend_port,
        api_key=api_key,
        remaining_seconds=deadline.remaining,
    )
    _wait_for_health(client, remaining_seconds=deadline.remaining)
    return client


def _cleanup_model(payload: Mapping[str, bool]) -> CleanupReceipt:
    if payload != {
        "attempted": True,
        "succeeded": True,
        "zero_unapproved_containers": True,
        "zero_unapproved_volumes": True,
        "zero_unapproved_networks": True,
        "zero_temp_residue": True,
    }:
        raise _error(FailureCode.CLEANUP_FAILED, FailurePhase.CLEANUP)
    return CleanupReceipt(
        attempted=True,
        succeeded=True,
        zero_container_residue=True,
        zero_volume_residue=True,
        zero_network_residue=True,
        zero_temp_residue=True,
    )


def _milliseconds(started: float, ended: float, maximum: int) -> int:
    value = max(0, int(round((ended - started) * 1000)))
    if value > maximum:
        raise _error(FailureCode.EVALUATION_INTERNAL_ERROR, FailurePhase.INTERNAL)
    return value


def _publish_diagnostic_best_effort(
    sink: DiagnosticSink | None,
    error: EvaluationError,
    *,
    remaining_seconds: Callable[[float], float],
) -> None:
    if sink is None or error.diagnostic is None:
        return
    try:
        publish_result_diagnostic(
            sink,
            error,
            remaining_seconds=remaining_seconds,
        )
    except Exception:
        return


def _close_live_configuration(configuration: Any) -> EvaluationError | None:
    try:
        configuration.close()
    except BaseException as exc:
        failure = EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        )
        failure.__cause__ = exc
        return failure
    return None


def observe_live(
    *,
    env_file: Path,
    provider_id: str,
    provider_base_url: str,
    primary_model_id: str,
    fallback_model_id: str,
    pricing_basis: str | None = None,
    currency: str | None = None,
    retain_task_images: bool = False,
    diagnostic_dir: Path | None = None,
    repository_root: Path = PROJECT_ROOT,
) -> LiveReportModel:
    """Execute one managed live observation.

    The Docker lifecycle implementation is intentionally imported only on this
    explicitly authorized path. Task-owned cleanup remains mandatory.
    """

    from scripts.bounded_live_producer_lifecycle import (
        LIVE_BUDGET,
        ActiveDeadline,
        CredentialDeclaration,
        ManagedComposeProject,
        cleanup_receipt,
        load_live_configuration,
        prepare_source_snapshot,
        run_bounded_subprocess,
        sanitize_compose_projection,
    )

    clock = time.monotonic
    total_deadline = ActiveDeadline(
        LIVE_BUDGET.total_wall_seconds,
        code=FailureCode.EVALUATION_INTERNAL_ERROR,
        phase=FailurePhase.INTERNAL,
        monotonic=clock,
    )
    non_cleanup_deadline = total_deadline.child(
        LIVE_BUDGET.total_wall_seconds - LIVE_BUDGET.cleanup_seconds,
        code=FailureCode.EVALUATION_INTERNAL_ERROR,
        phase=FailurePhase.INTERNAL,
    )
    _preflight_output_paths(repository_root)
    try:
        diagnostic_sink = (
            preflight_diagnostic_dir(
                diagnostic_dir,
                repository_root=repository_root,
            )
            if diagnostic_dir is not None
            else None
        )
    except DiagnosticOutputError as exc:
        raise _error(FailureCode.OUTPUT_INVALID, FailurePhase.INPUT) from exc
    non_cleanup_deadline.remaining(1.0)
    manifest = load_manifest(
        repository_root
        / "benchmarks"
        / "bounded-live-producer-v1"
        / "manifest.json"
    )
    non_cleanup_deadline.remaining(1.0)
    try:
        declaration = CredentialDeclaration(
            provider_id=provider_id,
            provider_base_url=provider_base_url,
            primary_model=primary_model_id,
            fallback_model=fallback_model_id,
            pricing_basis=pricing_basis,
            pricing_currency=currency,
        )
    except (TypeError, ValueError) as exc:
        raise _error(
            FailureCode.CREDENTIAL_SOURCE_INVALID,
            FailurePhase.INPUT,
        ) from exc
    non_cleanup_deadline.remaining(1.0)
    process_api_key = os.environ.get("DECISION_RESEARCH_AGENT_API_KEY", "")
    live_configuration = load_live_configuration(
        env_file,
        declaration,
        process_api_key=process_api_key,
        repository_root=repository_root,
    )
    try:
        non_cleanup_deadline.remaining(1.0)
    except BaseException:
        live_configuration.close()
        raise
    task_temp_parent: Path | None = None
    try:
        docker_environment = _scrubbed_docker_environment()
        probe_started = clock()
        probe_deadline = non_cleanup_deadline.child(
            LIVE_BUDGET.docker_probe_seconds,
            code=FailureCode.DOCKER_UNAVAILABLE,
            phase=FailurePhase.DOCKER,
        )
        docker_version = run_bounded_subprocess(
            ("docker", "version", "--format", "{{.Client.Version}}"),
            cwd=repository_root,
            env=docker_environment,
            deadline=probe_deadline,
            allowed_environment=_DOCKER_PROCESS_ENV,
        )
        compose_version = run_bounded_subprocess(
            ("docker", "compose", "version", "--short"),
            cwd=repository_root,
            env=docker_environment,
            deadline=probe_deadline,
            allowed_environment=_DOCKER_PROCESS_ENV,
        )
        docker_version_value = _bounded_public_version(
            docker_version.stdout,
            code=FailureCode.DOCKER_UNAVAILABLE,
        )
        compose_version_value = _bounded_public_version(
            compose_version.stdout,
            code=FailureCode.DOCKER_UNAVAILABLE,
        )
        probe_ms = _milliseconds(probe_started, clock(), 30_000)
        non_cleanup_deadline.remaining(1.0)

        task_temp_parent = Path(tempfile.gettempdir()) / (
            f"dra-bounded-producer-{secrets.token_hex(16)}"
        )
        required_paths = (
            "VERSION",
            "Dockerfile.backend",
            "docker-compose.yml",
            "benchmarks/bounded-live-producer-v1/manifest.json",
            "scripts/secure_local_runtime_proof.py",
            "scripts/bounded_live_producer_contracts.py",
            "scripts/bounded_live_producer_diagnostics.py",
            "scripts/bounded_live_producer_http.py",
            "scripts/bounded_live_producer_lifecycle.py",
            "scripts/bounded_live_producer_proof.py",
        )
        active_started = clock()
        active_deadline = non_cleanup_deadline.child(
            LIVE_BUDGET.active_seconds,
            code=FailureCode.SERVICE_START_FAILED,
            phase=FailurePhase.DOCKER,
        )
        snapshot = prepare_source_snapshot(
            repository_root,
            task_temp_parent,
            required_paths=required_paths,
            deadline=active_deadline,
            verify_secure_runtime=False,
        )
        snapshot_manifest_path = (
            snapshot.root
            / "benchmarks"
            / "bounded-live-producer-v1"
            / "manifest.json"
        )
        snapshot_manifest = load_manifest(snapshot_manifest_path)
        if snapshot_manifest != manifest:
            raise _error(FailureCode.SOURCE_ARCHIVE_INVALID, FailurePhase.DOCKER)
        manifest_sha256 = hashlib.sha256(snapshot_manifest_path.read_bytes()).hexdigest()
        project_name = f"dra-proof-{secrets.token_hex(16)}"
        project = ManagedComposeProject(
            root=snapshot.root,
            compose_paths=(snapshot.root / "docker-compose.yml",),
            env_file=live_configuration,
            project_name=project_name,
            environment=docker_environment,
            retain_image=retain_task_images,
        )
        project.track_temp_paths((task_temp_parent,))
        active_deadline.remaining(1.0)
    except BaseException as primary_error:
        try:
            if task_temp_parent is not None:
                cleanup_deadline = total_deadline.child(
                    LIVE_BUDGET.cleanup_seconds,
                    code=FailureCode.CLEANUP_FAILED,
                    phase=FailurePhase.CLEANUP,
                )

                def raise_primary() -> None:
                    raise primary_error

                def cleanup_pre_guard() -> CleanupReceipt:
                    return _cleanup_pre_guard_task_temp(
                        task_temp_parent,
                        remaining_seconds=cleanup_deadline.remaining,
                    )

                run_cleanup_guarded(raise_primary, cleanup_pre_guard)
            raise
        finally:
            live_configuration.close()

    cleanup_started = 0.0

    def primary() -> dict[str, Any]:
        project.assert_unclaimed(active_deadline)
        build_started = clock()
        build_deadline = active_deadline.child(
            LIVE_BUDGET.build_start_seconds,
            code=FailureCode.IMAGE_BUILD_FAILED,
            phase=FailurePhase.DOCKER,
        )
        config_raw = _project_result(
            project,
            ("config", "--format", "json"),
            build_deadline,
            compose=True,
        )
        try:
            resolved_config = json.loads(config_raw)
        except json.JSONDecodeError as exc:
            raise _error(FailureCode.COMPOSE_CONFIG_INVALID, FailurePhase.DOCKER) from exc
        sanitized_config = sanitize_compose_projection(resolved_config)
        sanitized_compose_sha256 = hashlib.sha256(
            json.dumps(
                sanitized_config,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        project.build_backend(build_deadline)
        secure_check_deadline = build_deadline.child(
            LIVE_BUDGET.build_start_seconds,
            code=FailureCode.SOURCE_ARCHIVE_INVALID,
            phase=FailurePhase.DOCKER,
        )
        project.verify_snapshot_secure_runtime(secure_check_deadline)
        image_tag = f"{project_name}-backend"
        image_id = _project_result(
            project,
            ("docker", "image", "inspect", "--format", "{{.Id}}", image_tag),
            build_deadline,
        )
        if not (
            image_id.startswith("sha256:")
            and len(image_id) == 71
            and all(character in "0123456789abcdef" for character in image_id[7:])
        ):
            raise _error(FailureCode.IMAGE_BUILD_FAILED, FailurePhase.DOCKER)
        project._image_tag = image_tag
        project._image_id = image_id
        project.start_mysql(build_deadline)
        _project_resource_ids(project, build_deadline)
        project.start_backend(build_deadline)
        _project_resource_ids(project, build_deadline)
        backend_port = _loopback_port(project, "backend", 8000, build_deadline)
        _loopback_port(project, "mysql", 3306, build_deadline)
        build_client = ProofHttpClient(
            port=backend_port,
            api_key=process_api_key,
            remaining_seconds=build_deadline.remaining,
        )
        _wait_for_health(build_client, remaining_seconds=build_deadline.remaining)
        build_start_ms = _milliseconds(build_started, clock(), 1_200_000)

        research_started = clock()
        research_deadline = active_deadline.child(
            LIVE_BUDGET.research_seconds,
            code=FailureCode.RUN_OBSERVATION_DEADLINE,
            phase=FailurePhase.OBSERVE,
        )
        request_bytes, request_sha256, thread_id, key = _new_request(manifest)
        research_client = ProofHttpClient(
            port=backend_port,
            api_key=process_api_key,
            remaining_seconds=research_deadline.remaining,
        )
        accepted = reconcile_create(
            research_client,
            request_bytes=request_bytes,
            key=key,
        )
        if accepted["thread_id"] != thread_id:
            raise _error(FailureCode.CREATE_IDENTITY_MISMATCH, FailurePhase.CREATE)
        before, _status, _result = observe_terminal(
            research_client,
            accepted=accepted,
            required_cited_domains=manifest.required_cited_domains,
            remaining_seconds=research_deadline.remaining,
        )
        usage = observe_usage(
            research_client.usage(
                run_id=accepted["run_id"],
                timeout_seconds=30.0,
            ),
            primary_model_id=primary_model_id,
            fallback_model_id=fallback_model_id,
            pricing_basis=pricing_basis,
            currency=currency,
            pricing_identity_matches=(
                pricing_basis is not None
                and currency is not None
                and live_configuration.get("TOKEN_PRICING_BASIS") == pricing_basis
                and live_configuration.get("TOKEN_PRICING_CURRENCY") == currency
            ),
        )
        research_ms = _milliseconds(research_started, clock(), 1_800_000)

        restart_started = clock()
        restart_deadline = active_deadline.child(
            LIVE_BUDGET.restart_replay_seconds,
            code=FailureCode.BACKEND_RESTART_FAILED,
            phase=FailurePhase.RESTART,
        )
        restart_client = restart_backend_transport(
            project,
            api_key=process_api_key,
            deadline=restart_deadline,
        )
        after_restart, _status, _result = observe_terminal(
            restart_client,
            accepted=accepted,
            required_cited_domains=manifest.required_cited_domains,
            remaining_seconds=restart_deadline.remaining,
        )
        restart_receipt = compare_restart(before, after_restart)
        replay_ack = restart_client.create(
            request_bytes=request_bytes,
            idempotency_key=key,
            timeout_seconds=30.0,
        )
        after_replay, _status, _result = observe_terminal(
            restart_client,
            accepted=accepted,
            required_cited_domains=manifest.required_cited_domains,
            remaining_seconds=restart_deadline.remaining,
        )
        replay_receipt = validate_replay(
            replay_ack,
            before=after_restart,
            after=after_replay,
        )
        restart_replay_ms = _milliseconds(
            restart_started,
            clock(),
            300_000,
        )
        active_deadline.remaining(1.0)
        return {
            "sanitized_compose_sha256": sanitized_compose_sha256,
            "image_id": image_id,
            "request_sha256": request_sha256,
            "terminal": before,
            "usage": usage,
            "restart": restart_receipt,
            "replay": replay_receipt,
            "build_start_ms": build_start_ms,
            "research_ms": research_ms,
            "restart_replay_ms": restart_replay_ms,
        }

    def cleanup() -> CleanupReceipt:
        nonlocal cleanup_started
        cleanup_started = clock()
        cleanup_deadline = total_deadline.child(
            LIVE_BUDGET.cleanup_seconds,
            code=FailureCode.CLEANUP_FAILED,
            phase=FailurePhase.CLEANUP,
        )
        refresh_error: BaseException | None = None
        if project._project_claimed:
            try:
                _project_resource_ids(project, cleanup_deadline)
            except BaseException as exc:
                refresh_error = exc
        try:
            receipt = _cleanup_model(cleanup_receipt(project, cleanup_deadline))
        except BaseException as cleanup_error:
            if refresh_error is not None:
                raise BaseExceptionGroup(
                    "bounded cleanup refresh and removal failures",
                    [refresh_error, cleanup_error],
                )
            raise
        if refresh_error is not None:
            raise EvaluationError(
                FailureCode.CLEANUP_FAILED,
                FailurePhase.CLEANUP,
                False,
                CleanupStatus.FAILED,
            ) from refresh_error
        return receipt

    try:
        facts, cleanup_model = run_cleanup_guarded(primary, cleanup)
    except EvaluationError as exc:
        final_error = EvaluationError(
            exc.code,
            exc.phase,
            exc.retryable,
            (
                CleanupStatus.FAILED
                if exc.phase is FailurePhase.CLEANUP
                or exc.cleanup_status is CleanupStatus.FAILED
                else CleanupStatus.SUCCEEDED
            ),
            diagnostic=exc.diagnostic,
        )
        close_failure = _close_live_configuration(live_configuration)
        cause: BaseException = exc
        if close_failure is not None:
            final_error = EvaluationError(
                final_error.code,
                final_error.phase,
                final_error.retryable,
                CleanupStatus.FAILED,
                diagnostic=final_error.diagnostic,
            )
            cause = BaseExceptionGroup(
                "bounded primary and configuration cleanup failures",
                [exc, close_failure],
            )
        _publish_diagnostic_best_effort(
            diagnostic_sink,
            final_error,
            remaining_seconds=total_deadline.remaining,
        )
        raise final_error from cause
    except BaseExceptionGroup as exc:
        cause = exc
        close_failure = _close_live_configuration(live_configuration)
        if close_failure is not None:
            cause = BaseExceptionGroup(
                "bounded grouped and configuration cleanup failures",
                [exc, close_failure],
            )
        final_error = _group_error(cause)
        _publish_diagnostic_best_effort(
            diagnostic_sink,
            final_error,
            remaining_seconds=total_deadline.remaining,
        )
        raise final_error from cause
    except BaseException as exc:
        close_failure = _close_live_configuration(live_configuration)
        if close_failure is not None:
            raise BaseExceptionGroup(
                "bounded unknown and configuration cleanup failures",
                [exc, close_failure],
            ) from exc
        raise
    try:
        cleanup_ms = _milliseconds(cleanup_started, clock(), 120_000)
        active_ms = _milliseconds(active_started, cleanup_started, 3_300_000)
        active_ms = max(
            active_ms,
            facts["build_start_ms"]
            + facts["research_ms"]
            + facts["restart_replay_ms"],
        )
        total_ms = probe_ms + active_ms + cleanup_ms
        total_deadline.remaining(1.0)
        terminal = facts["terminal"]
        report = LiveReportModel.model_validate(
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "status": "valid",
                "source": {
                    "repository_name": "decision-research-agent",
                    "service_name": "decision-research-agent",
                    "version": snapshot.version,
                    "source_commit": snapshot.commit,
                    "source_tree": snapshot.tree,
                    "archive_sha256": snapshot.archive_sha256,
                    "manifest_sha256": manifest_sha256,
                    "sanitized_compose_sha256": facts["sanitized_compose_sha256"],
                    "backend_image_id": facts["image_id"],
                    "docker_version": docker_version_value,
                    "compose_version": compose_version_value,
                    "source_clean": True,
                    "build_context": "tracked_archive",
                },
                "scenario": {
                    "scenario_id": manifest.scenario_id,
                    "manifest_sha256": manifest_sha256,
                    "request_sha256": facts["request_sha256"],
                    "profile_id": manifest.profile_id,
                    "required_cited_domains": list(manifest.required_cited_domains),
                    "provider_id": provider_id,
                    "primary_model_id": primary_model_id,
                    "fallback_model_id": fallback_model_id,
                },
                "lifecycle": {
                    "docker_probe_ms": probe_ms,
                    "build_start_ms": facts["build_start_ms"],
                    "research_ms": facts["research_ms"],
                    "restart_replay_ms": facts["restart_replay_ms"],
                    "active_ms": active_ms,
                    "cleanup_ms": cleanup_ms,
                    "total_ms": total_ms,
                    "loopback_binding_observed": True,
                    "health_identity_observed": True,
                },
                "run": terminal.run.model_dump(mode="python"),
                "result": terminal.result.model_dump(mode="python"),
                "evidence": [row.model_dump(mode="python") for row in terminal.evidence],
                "usage": facts["usage"].model_dump(mode="python"),
                "restart": facts["restart"].model_dump(mode="python"),
                "replay": facts["replay"].model_dump(mode="python"),
                "cleanup": cleanup_model.model_dump(mode="python"),
                "boundaries": BOUNDARIES,
                "limits": list(LIMITS),
            },
            strict=True,
        )
        total_deadline.remaining(1.0)
        publish_paired_output(
            repository_root,
            report,
            remaining_seconds=total_deadline.remaining,
        )
        return report
    except EvaluationError as exc:
        raise EvaluationError(
            exc.code,
            exc.phase,
            exc.retryable,
            CleanupStatus.SUCCEEDED,
            diagnostic=exc.diagnostic,
        ) from exc
    except ValidationError as exc:
        raise EvaluationError(
            FailureCode.REPORT_INVALID,
            FailurePhase.OUTPUT,
            False,
            CleanupStatus.SUCCEEDED,
        ) from exc
    except BaseException as exc:
        raise EvaluationError(
            FailureCode.EVALUATION_INTERNAL_ERROR,
            FailurePhase.INTERNAL,
            False,
            CleanupStatus.SUCCEEDED,
        ) from exc
    finally:
        live_configuration.close()


class _ParserExit(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


class _StableArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _error(FailureCode.MANIFEST_INVALID, FailurePhase.INPUT)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, sys.stdout if status == 0 else sys.stderr)
        raise _ParserExit(status)


def _parser() -> argparse.ArgumentParser:
    parser = _StableArgumentParser(
        prog="bounded_live_producer_proof.py",
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", allow_abbrev=False)
    live = commands.add_parser("observe-live", allow_abbrev=False)
    live.add_argument("--env-file", required=True, type=Path)
    live.add_argument("--provider-id", required=True)
    live.add_argument("--provider-base-url", required=True)
    live.add_argument("--primary-model-id", required=True)
    live.add_argument("--fallback-model-id", required=True)
    live.add_argument("--pricing-basis")
    live.add_argument("--currency")
    live.add_argument("--retain-task-images", action="store_true")
    live.add_argument("--diagnostic-dir", type=Path)
    return parser


def _validation_error(error: EvaluationValidationError) -> EvaluationError:
    mapping = {
        "manifest_invalid": (FailureCode.MANIFEST_INVALID, FailurePhase.INPUT),
        "usage_invalid": (FailureCode.USAGE_INVALID, FailurePhase.USAGE),
        "evidence_invalid": (FailureCode.EVIDENCE_INVALID, FailurePhase.EVIDENCE),
        "report_invalid": (FailureCode.REPORT_INVALID, FailurePhase.OUTPUT),
    }
    code, phase = mapping.get(
        error.code,
        (FailureCode.EVALUATION_INTERNAL_ERROR, FailurePhase.INTERNAL),
    )
    return _error(code, phase)


def _group_error(group: BaseExceptionGroup) -> EvaluationError:
    leaves: list[BaseException] = []

    def collect(error: BaseException) -> None:
        if isinstance(error, BaseExceptionGroup):
            for nested in error.exceptions:
                collect(nested)
        else:
            leaves.append(error)

    collect(group)
    errors = [item for item in leaves if isinstance(item, EvaluationError)]
    cleanup_failed = any(
        item.phase is FailurePhase.CLEANUP
        or item.cleanup_status is CleanupStatus.FAILED
        for item in errors
    )
    primary = next(
        (item for item in errors if item.phase is not FailurePhase.CLEANUP),
        None,
    )
    unknown_primary = next(
        (item for item in leaves if not isinstance(item, EvaluationError)),
        None,
    )
    if primary is None:
        if unknown_primary is not None:
            return EvaluationError(
                FailureCode.EVALUATION_INTERNAL_ERROR,
                FailurePhase.INTERNAL,
                False,
                CleanupStatus.FAILED if cleanup_failed else CleanupStatus.NOT_STARTED,
            )
        return EvaluationError(
            FailureCode.CLEANUP_FAILED,
            FailurePhase.CLEANUP,
            False,
            CleanupStatus.FAILED,
        )
    return EvaluationError(
        primary.code,
        primary.phase,
        primary.retryable,
        CleanupStatus.FAILED if cleanup_failed else primary.cleanup_status,
        diagnostic=primary.diagnostic,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        try:
            arguments = _parser().parse_args(argv)
        except _ParserExit as exit_request:
            return exit_request.status
        if arguments.command == "check":
            result: dict[str, Any] = run_provider_free_check()
        else:
            if (arguments.pricing_basis is None) != (arguments.currency is None):
                raise _error(FailureCode.CREDENTIAL_SOURCE_INVALID, FailurePhase.INPUT)
            report = observe_live(
                env_file=arguments.env_file,
                provider_id=arguments.provider_id,
                provider_base_url=arguments.provider_base_url,
                primary_model_id=arguments.primary_model_id,
                fallback_model_id=arguments.fallback_model_id,
                pricing_basis=arguments.pricing_basis,
                currency=arguments.currency,
                retain_task_images=arguments.retain_task_images,
                diagnostic_dir=arguments.diagnostic_dir,
            )
            result = {
                "mode": "live",
                "schema_version": REPORT_SCHEMA_VERSION,
                "status": report.status,
            }
        sys.stdout.buffer.write(_canonical_bytes(result) + b"\n")
        return 0
    except EvaluationValidationError as exc:
        error = _validation_error(exc)
    except EvaluationError as exc:
        error = exc
    except BaseExceptionGroup as exc:
        error = _group_error(exc)
    except BaseException:
        error = _error(
            FailureCode.EVALUATION_INTERNAL_ERROR,
            FailurePhase.INTERNAL,
        )
    sys.stderr.buffer.write(serialize_error(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
