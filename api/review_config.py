from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import uuid

from api.review_gate import ReviewGate
from api.review_models import durable_hitl_enabled
from api.review_repository import init_review_schema
from api.run_migrations import verify_run_schema


class ReviewConfigurationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReviewRuntimeConfig:
    enabled: bool
    application_db_path: Path | None = None
    checkpoint_db_path: Path | None = None
    output_dir: Path | None = None


@dataclass(frozen=True)
class ReviewRuntimeReadiness:
    application_schema_ready: bool
    checkpoint_compatible: bool
    gate_report_status: str

    @property
    def ready(self) -> bool:
        return (
            self.application_schema_ready
            and self.checkpoint_compatible
            and self.gate_report_status == "PASS"
        )


def _persistent_path(raw: str | None, *, missing_code: str, memory_code: str) -> Path:
    value = (raw or "").strip()
    if not value:
        raise ReviewConfigurationError(missing_code)
    if value == ":memory:":
        raise ReviewConfigurationError(memory_code)
    return Path(value).expanduser().resolve()


def _ensure_writable_parent(path: Path, *, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    probe = path.parent / f".review-write-probe-{uuid.uuid4().hex}"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("ok\n")
    except OSError as exc:
        raise ReviewConfigurationError(code) from exc
    finally:
        probe.unlink(missing_ok=True)


def validate_review_runtime(*, output_dir: Path) -> ReviewRuntimeConfig:
    if not durable_hitl_enabled():
        return ReviewRuntimeConfig(enabled=False)
    if not os.getenv("API_SECRET", ""):
        raise ReviewConfigurationError("review_auth_not_configured")

    application = _persistent_path(
        os.getenv("TASKS_DB_PATH"),
        missing_code="review_application_db_not_configured",
        memory_code="review_application_db_not_persistent",
    )
    checkpoint = _persistent_path(
        os.getenv("DECISION_RESEARCH_AGENT_CHECKPOINT_DB_PATH"),
        missing_code="review_checkpoint_db_not_configured",
        memory_code="review_checkpoint_db_not_persistent",
    )
    if application == checkpoint:
        raise ReviewConfigurationError("review_databases_must_be_separate")

    output = output_dir.resolve()
    _ensure_writable_parent(application, code="review_application_db_not_writable")
    _ensure_writable_parent(checkpoint, code="review_checkpoint_db_not_writable")
    output.mkdir(parents=True, exist_ok=True)
    _ensure_writable_parent(
        output / ".review-output-probe",
        code="review_output_not_writable",
    )
    return ReviewRuntimeConfig(
        enabled=True,
        application_db_path=application,
        checkpoint_db_path=checkpoint,
        output_dir=output,
    )


def check_review_readiness(
    *,
    runtime: ReviewRuntimeConfig,
    gate_report_path: Path,
) -> ReviewRuntimeReadiness:
    if not runtime.enabled:
        return ReviewRuntimeReadiness(False, False, "DISABLED")
    application_schema_ready = False
    checkpoint_compatible = False
    gate_report_status = "MISSING"
    try:
        init_review_schema(str(runtime.application_db_path))
        verify_run_schema(db_path=str(runtime.application_db_path))
        application_schema_ready = True
    except Exception:
        pass
    try:
        ReviewGate(
            str(runtime.checkpoint_db_path),
            lambda decision_id: None,
        ).inspect("review_runtime_probe")
        checkpoint_compatible = True
    except Exception:
        pass
    try:
        report = json.loads(gate_report_path.read_text(encoding="utf-8"))
        if (
            report.get("expected") == 13
            and report.get("passed") == 13
            and report.get("failed") == []
        ):
            gate_report_status = report.get("status", "INVALID")
        else:
            gate_report_status = "INVALID"
    except (OSError, ValueError, TypeError):
        pass
    return ReviewRuntimeReadiness(
        application_schema_ready=application_schema_ready,
        checkpoint_compatible=checkpoint_compatible,
        gate_report_status=gate_report_status,
    )
