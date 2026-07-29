"""Pure closed lifecycle authority for persisted run recovery state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from typing import Callable

from api.run_dispatch_models import MAX_RUN_DISPATCH_ATTEMPTS


class LifecycleStateInvalid(ValueError):
    pass


class LifecycleRole(StrEnum):
    ORDINARY = "ordinary"
    RECOVERY_SOURCE = "recovery_source"
    RECOVERY_REPLACEMENT = "recovery_replacement"


class LifecycleFamily(StrEnum):
    ORDINARY_COMPATIBLE = "ordinary_compatible"
    INITIAL_PENDING = "initial_pending"
    RETRY_PENDING = "retry_pending"
    LEASED = "leased"
    RUNNING_EXECUTION = "running_execution"
    RUNNING_FINALIZATION = "running_finalization"
    PRESTART_FAILED = "prestart_failed"
    DISPATCH_EXHAUSTED = "dispatch_exhausted"
    CLOSED_TERMINAL = "closed_terminal"
    LATER_BOOT_INTERRUPTED = "later_boot_interrupted"


@dataclass(frozen=True, slots=True)
class RecoveryLifecycleSnapshot:
    run_id: str
    dispatch_status: str
    lease_owner: object
    lease_expires_at: object
    attempt_count: int
    last_error_code: object
    dispatch_created_at: object
    dispatch_updated_at: object
    started_at: object
    execution_status: str
    review_status: str
    delivery_status: str
    state_version: int
    run_created_at: object
    run_updated_at: object
    segment_id: object
    segment_run_id: object
    kind: object
    sequence: object
    segment_attempt: object
    segment_status: object
    segment_created_at: object
    segment_updated_at: object
    owner_segment_id: object
    owner_status: object
    owner_phase: object
    owner_boot_id: object
    owner_id: object
    owner_created_at: object
    owner_phase_updated_at: object
    owner_closed_at: object
    recovery_reason: object
    observation_status: object
    terminal_state_version: object
    cause_phase: object
    cause_code: object
    recorded_at: object
    initial_segment_count: int


_Matcher = Callable[[RecoveryLifecycleSnapshot, str | None], bool]
_DISPATCH_CODES = frozenset(
    {
        "run_dispatch_schedule_failed",
        "run_dispatch_start_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
    }
)
_EXECUTION_CODES = frozenset(
    {
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
        "run_timeout",
        "cancelled",
        "execution_error",
    }
)
_FINALIZATION_CODES = frozenset(
    {"run_timeout", "cancelled", "run_finalization_failed"}
)


def _reject() -> None:
    raise LifecycleStateInvalid("lifecycle_state_invalid")


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _identifier(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(rf"{re.escape(prefix)}[0-9a-f]{{32}}", value) is not None
    )


def _bounded_code(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None
    )


def _base(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        isinstance(snapshot.run_id, str)
        and bool(snapshot.run_id)
        and snapshot.initial_segment_count == 1
        and snapshot.segment_id == f"{snapshot.run_id}_seg_000"
        and snapshot.segment_run_id == snapshot.run_id
        and snapshot.kind == "initial"
        and snapshot.sequence == 0
        and snapshot.segment_attempt == 1
        and _timestamp(snapshot.dispatch_created_at)
        and _timestamp(snapshot.dispatch_updated_at)
        and _timestamp(snapshot.run_created_at)
        and _timestamp(snapshot.run_updated_at)
        and _timestamp(snapshot.segment_created_at)
        and _timestamp(snapshot.segment_updated_at)
        and snapshot.review_status in {"not_required", "required", "resolved"}
        and snapshot.delivery_status
        in {"pending", "ready", "review_required", "blocked", "failed"}
        and isinstance(snapshot.attempt_count, int)
        and not isinstance(snapshot.attempt_count, bool)
        and isinstance(snapshot.state_version, int)
        and not isinstance(snapshot.state_version, bool)
    )


def _no_owner(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        snapshot.owner_segment_id is None
        and snapshot.owner_status is None
        and snapshot.owner_phase is None
        and snapshot.owner_boot_id is None
        and snapshot.owner_id is None
        and snapshot.owner_created_at is None
        and snapshot.owner_phase_updated_at is None
        and snapshot.owner_closed_at is None
        and snapshot.recovery_reason is None
    )


def _no_cause(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        snapshot.observation_status is None
        and snapshot.terminal_state_version is None
        and snapshot.cause_phase is None
        and snapshot.cause_code is None
        and snapshot.recorded_at is None
    )


def _pending_run(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        snapshot.execution_status == "pending"
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "pending"
        and snapshot.state_version == 0
        and snapshot.segment_status == "pending"
        and snapshot.run_updated_at == snapshot.run_created_at
        and snapshot.segment_updated_at == snapshot.segment_created_at
        and _no_owner(snapshot)
        and _no_cause(snapshot)
    )


def _pending_dispatch(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        snapshot.dispatch_status == "pending"
        and snapshot.lease_owner is None
        and snapshot.lease_expires_at is None
        and snapshot.started_at is None
    )


def _started_dispatch(snapshot: RecoveryLifecycleSnapshot) -> bool:
    return (
        snapshot.dispatch_status == "started"
        and 1 <= snapshot.attempt_count <= MAX_RUN_DISPATCH_ATTEMPTS
        and snapshot.lease_owner is None
        and snapshot.lease_expires_at is None
        and snapshot.last_error_code is None
        and _timestamp(snapshot.started_at)
        and snapshot.dispatch_updated_at == snapshot.started_at
    )


def _dispatch_shape(snapshot: RecoveryLifecycleSnapshot) -> bool:
    if snapshot.dispatch_status == "pending":
        return (
            _pending_dispatch(snapshot)
            and (
                (
                    snapshot.attempt_count == 0
                    and snapshot.last_error_code is None
                )
                or (
                    1 <= snapshot.attempt_count < MAX_RUN_DISPATCH_ATTEMPTS
                    and _bounded_code(snapshot.last_error_code)
                )
            )
        )
    if snapshot.dispatch_status == "leased":
        return (
            1 <= snapshot.attempt_count <= MAX_RUN_DISPATCH_ATTEMPTS
            and _identifier(snapshot.lease_owner, "dispatch_worker_")
            and _timestamp(snapshot.lease_expires_at)
            and snapshot.started_at is None
        )
    if snapshot.dispatch_status == "started":
        return _started_dispatch(snapshot)
    return (
        snapshot.dispatch_status == "failed"
        and snapshot.attempt_count == MAX_RUN_DISPATCH_ATTEMPTS
        and snapshot.lease_owner is None
        and snapshot.lease_expires_at is None
        and _bounded_code(snapshot.last_error_code)
        and snapshot.started_at is None
    )


def _cause(
    snapshot: RecoveryLifecycleSnapshot,
    *,
    version: int,
    phase: str,
    codes: frozenset[str],
    timestamp: object,
) -> bool:
    return (
        snapshot.observation_status == "observed"
        and snapshot.terminal_state_version == version
        and snapshot.cause_phase == phase
        and snapshot.cause_code in codes
        and snapshot.recorded_at == timestamp
        and _timestamp(timestamp)
    )


def _initial_pending(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    return (
        _base(snapshot)
        and _pending_run(snapshot)
        and _pending_dispatch(snapshot)
        and snapshot.attempt_count == 0
        and snapshot.last_error_code is None
        and snapshot.dispatch_updated_at == snapshot.dispatch_created_at
    )


def _retry_pending(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    return (
        _base(snapshot)
        and _pending_run(snapshot)
        and _pending_dispatch(snapshot)
        and 1 <= snapshot.attempt_count < MAX_RUN_DISPATCH_ATTEMPTS
        and _bounded_code(snapshot.last_error_code)
    )


def _leased(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    return (
        _base(snapshot)
        and _pending_run(snapshot)
        and snapshot.dispatch_status == "leased"
        and 1 <= snapshot.attempt_count <= MAX_RUN_DISPATCH_ATTEMPTS
        and _identifier(snapshot.lease_owner, "dispatch_worker_")
        and _timestamp(snapshot.lease_expires_at)
        and snapshot.started_at is None
        and (
            (
                snapshot.attempt_count == 1
                and snapshot.last_error_code is None
            )
            or (
                snapshot.attempt_count > 1
                and (
                    snapshot.last_error_code is None
                    or _bounded_code(snapshot.last_error_code)
                )
            )
        )
    )


def _running(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
    *,
    phase: str,
) -> bool:
    return (
        _base(snapshot)
        and _started_dispatch(snapshot)
        and snapshot.execution_status == "running"
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "pending"
        and snapshot.state_version == 1
        and snapshot.segment_status == "running"
        and snapshot.run_updated_at == snapshot.started_at
        and snapshot.segment_updated_at == snapshot.started_at
        and snapshot.owner_segment_id == snapshot.segment_id
        and snapshot.owner_status == "active"
        and snapshot.owner_phase == phase
        and current_boot_id is not None
        and snapshot.owner_boot_id == current_boot_id
        and _identifier(snapshot.owner_id, "owner_")
        and snapshot.owner_created_at == snapshot.started_at
        and _timestamp(snapshot.owner_phase_updated_at)
        and snapshot.owner_closed_at is None
        and snapshot.recovery_reason is None
        and _no_cause(snapshot)
    )


def _running_execution(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    return _running(snapshot, current_boot_id, phase="execution")


def _running_finalization(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    return _running(snapshot, current_boot_id, phase="finalization")


def _prestart_failed(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    dispatch_is_pending = (
        _pending_dispatch(snapshot)
        and (
            (
                snapshot.attempt_count == 0
                and snapshot.last_error_code is None
            )
            or (
                1 <= snapshot.attempt_count < MAX_RUN_DISPATCH_ATTEMPTS
                and _bounded_code(snapshot.last_error_code)
            )
        )
    )
    dispatch_is_leased = (
        snapshot.dispatch_status == "leased"
        and 1 <= snapshot.attempt_count <= MAX_RUN_DISPATCH_ATTEMPTS
        and _identifier(snapshot.lease_owner, "dispatch_worker_")
        and _timestamp(snapshot.lease_expires_at)
        and snapshot.started_at is None
        and (
            snapshot.last_error_code is None
            or _bounded_code(snapshot.last_error_code)
        )
    )
    return (
        _base(snapshot)
        and (dispatch_is_pending or dispatch_is_leased)
        and snapshot.execution_status == "failed"
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "failed"
        and snapshot.state_version == 1
        and snapshot.segment_status == "failed"
        and snapshot.run_updated_at == snapshot.segment_updated_at
        and _no_owner(snapshot)
        and snapshot.cause_phase in {"execution", "finalization"}
        and _cause(
            snapshot,
            version=1,
            phase=snapshot.cause_phase,
            codes=(
                _EXECUTION_CODES
                if snapshot.cause_phase == "execution"
                else _FINALIZATION_CODES
            ),
            timestamp=snapshot.run_updated_at,
        )
    )


def _dispatch_exhausted(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    return (
        _base(snapshot)
        and snapshot.dispatch_status == "failed"
        and snapshot.attempt_count == MAX_RUN_DISPATCH_ATTEMPTS
        and snapshot.lease_owner is None
        and snapshot.lease_expires_at is None
        and snapshot.started_at is None
        and snapshot.last_error_code in _DISPATCH_CODES
        and snapshot.execution_status == "failed"
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "failed"
        and snapshot.state_version == 1
        and snapshot.segment_status == "failed"
        and snapshot.run_updated_at
        == snapshot.segment_updated_at
        == snapshot.dispatch_updated_at
        and _no_owner(snapshot)
        and _cause(
            snapshot,
            version=1,
            phase="dispatch",
            codes=frozenset({snapshot.last_error_code}),
            timestamp=snapshot.run_updated_at,
        )
    )


def _closed_terminal(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    terminal = snapshot.segment_updated_at
    common = (
        _base(snapshot)
        and _started_dispatch(snapshot)
        and snapshot.execution_status
        in {"completed", "completed_with_fallback", "failed"}
        and snapshot.segment_status == snapshot.execution_status
        and snapshot.state_version >= 2
        and (
            snapshot.state_version > 2
            or snapshot.run_updated_at == terminal
        )
        and snapshot.owner_segment_id == snapshot.segment_id
        and snapshot.owner_status == "closed"
        and snapshot.owner_boot_id is None
        and snapshot.owner_id is None
        and _timestamp(snapshot.owner_created_at)
        and snapshot.owner_phase_updated_at
        == snapshot.owner_closed_at
        == terminal
        and snapshot.recovery_reason is None
    )
    if not common:
        return False
    if snapshot.execution_status in {"completed", "completed_with_fallback"}:
        return (
            snapshot.owner_phase == "finalization"
            and (
                (
                    snapshot.review_status == "not_required"
                    and snapshot.delivery_status == "ready"
                )
                or (
                    snapshot.review_status == "required"
                    and snapshot.delivery_status == "review_required"
                )
                or (
                    snapshot.review_status == "resolved"
                    and snapshot.delivery_status in {"ready", "blocked"}
                )
            )
            and _no_cause(snapshot)
        )
    return (
        snapshot.state_version == 2
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "failed"
        and snapshot.owner_phase in {"execution", "finalization"}
        and snapshot.cause_phase in {"execution", "finalization"}
        and _cause(
            snapshot,
            version=2,
            phase=snapshot.cause_phase,
            codes=(
                _EXECUTION_CODES
                if snapshot.cause_phase == "execution"
                else _FINALIZATION_CODES
            ),
            timestamp=terminal,
        )
    )


def _later_boot_interrupted(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    del current_boot_id
    terminal = snapshot.run_updated_at
    expected_code = {
        "execution": "execution_error",
        "finalization": "run_finalization_failed",
    }.get(snapshot.owner_phase)
    return (
        _base(snapshot)
        and _started_dispatch(snapshot)
        and snapshot.execution_status == "failed"
        and snapshot.review_status == "not_required"
        and snapshot.delivery_status == "failed"
        and snapshot.state_version == 2
        and snapshot.segment_status == "failed"
        and snapshot.segment_updated_at == terminal
        and snapshot.owner_segment_id == snapshot.segment_id
        and snapshot.owner_status == "interrupted"
        and snapshot.owner_boot_id is None
        and snapshot.owner_id is None
        and _timestamp(snapshot.owner_created_at)
        and snapshot.owner_phase_updated_at
        == snapshot.owner_closed_at
        == terminal
        and snapshot.recovery_reason
        in {"previous_boot_interrupted", "pre_v1_running_without_owner"}
        and expected_code is not None
        and _cause(
            snapshot,
            version=2,
            phase=snapshot.owner_phase,
            codes=frozenset({expected_code}),
            timestamp=terminal,
        )
    )


def _ordinary_compatible(
    snapshot: RecoveryLifecycleSnapshot,
    current_boot_id: str | None,
) -> bool:
    if (
        _base(snapshot)
        and _dispatch_shape(snapshot)
        and _no_owner(snapshot)
        and (
            snapshot.dispatch_status in {"pending", "leased"}
            or (
                snapshot.dispatch_status == "started"
                and snapshot.execution_status != "running"
            )
        )
    ):
        return True
    if any(
        matcher(snapshot, current_boot_id)
        for matcher in (
            _initial_pending,
            _retry_pending,
            _leased,
            _running_execution,
            _running_finalization,
            _prestart_failed,
            _dispatch_exhausted,
            _closed_terminal,
            _later_boot_interrupted,
        )
    ):
        return True
    terminal = snapshot.run_updated_at
    dispatch_unstarted = snapshot.dispatch_status in {"pending", "leased"}
    terminal_without_owner = (
        _base(snapshot)
        and (dispatch_unstarted or _started_dispatch(snapshot))
        and snapshot.execution_status
        in {"completed", "completed_with_fallback", "failed"}
        and snapshot.segment_status == snapshot.execution_status
        and snapshot.state_version >= 1
        and snapshot.segment_updated_at == terminal
        and _no_owner(snapshot)
    )
    if not terminal_without_owner:
        return False
    if snapshot.execution_status == "failed":
        return (
            snapshot.review_status == "not_required"
            and snapshot.delivery_status == "failed"
            and snapshot.cause_phase in {"dispatch", "execution", "finalization"}
            and _cause(
                snapshot,
                version=snapshot.state_version,
                phase=snapshot.cause_phase,
                codes={
                    "dispatch": _DISPATCH_CODES,
                    "execution": _EXECUTION_CODES,
                    "finalization": _FINALIZATION_CODES,
                }[snapshot.cause_phase],
                timestamp=terminal,
            )
        )
    return _no_cause(snapshot)


_CLOSED_MATCHERS: tuple[
    tuple[LifecycleRole, LifecycleFamily, _Matcher],
    ...,
] = (
    (
        LifecycleRole.ORDINARY,
        LifecycleFamily.ORDINARY_COMPATIBLE,
        _ordinary_compatible,
    ),
    (
        LifecycleRole.RECOVERY_SOURCE,
        LifecycleFamily.LATER_BOOT_INTERRUPTED,
        _later_boot_interrupted,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.INITIAL_PENDING,
        _initial_pending,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.RETRY_PENDING,
        _retry_pending,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.LEASED,
        _leased,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.RUNNING_EXECUTION,
        _running_execution,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.RUNNING_FINALIZATION,
        _running_finalization,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.PRESTART_FAILED,
        _prestart_failed,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.DISPATCH_EXHAUSTED,
        _dispatch_exhausted,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.CLOSED_TERMINAL,
        _closed_terminal,
    ),
    (
        LifecycleRole.RECOVERY_REPLACEMENT,
        LifecycleFamily.LATER_BOOT_INTERRUPTED,
        _later_boot_interrupted,
    ),
)


def classify_recovery_lifecycle(
    snapshot: RecoveryLifecycleSnapshot,
    *,
    role: LifecycleRole,
    current_boot_id: str | None,
) -> LifecycleFamily:
    matches = tuple(
        family
        for candidate_role, family, matcher in _CLOSED_MATCHERS
        if candidate_role is role and matcher(snapshot, current_boot_id)
    )
    if len(matches) != 1:
        _reject()
    return matches[0]
