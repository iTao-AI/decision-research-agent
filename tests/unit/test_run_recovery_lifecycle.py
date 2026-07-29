from __future__ import annotations

from dataclasses import fields, replace
import inspect

import pytest

from api.run_recovery_lifecycle import (
    LifecycleFamily,
    LifecycleRole,
    LifecycleStateInvalid,
    RecoveryLifecycleSnapshot,
    classify_recovery_lifecycle,
)


EXPECTED_ROLES = {
    "ordinary",
    "recovery_source",
    "recovery_replacement",
}
EXPECTED_FAMILIES = {
    "ordinary_compatible",
    "initial_pending",
    "retry_pending",
    "leased",
    "running_execution",
    "running_finalization",
    "prestart_failed",
    "dispatch_exhausted",
    "closed_terminal",
    "later_boot_interrupted",
}
FIELD_GROUPS = (
    "run",
    "segment",
    "dispatch",
    "owner",
    "cause",
    "boot",
    "timestamp",
    "lineage",
)

CREATED = "2026-07-29T00:00:00+00:00"
STARTED = "2026-07-29T00:01:00+00:00"
TERMINAL = "2026-07-29T00:02:00+00:00"
BOOT_ID = f"boot_{'a' * 32}"
WORKER_ID = f"dispatch_worker_{'b' * 32}"
OWNER_ID = f"owner_{'c' * 32}"


def _initial_pending() -> RecoveryLifecycleSnapshot:
    return RecoveryLifecycleSnapshot(
        run_id=f"run_{'d' * 32}",
        dispatch_status="pending",
        lease_owner=None,
        lease_expires_at=None,
        attempt_count=0,
        last_error_code=None,
        dispatch_created_at=CREATED,
        dispatch_updated_at=CREATED,
        started_at=None,
        execution_status="pending",
        review_status="not_required",
        delivery_status="pending",
        state_version=0,
        run_created_at=CREATED,
        run_updated_at=CREATED,
        segment_id=f"run_{'d' * 32}_seg_000",
        segment_run_id=f"run_{'d' * 32}",
        kind="initial",
        sequence=0,
        segment_attempt=1,
        segment_status="pending",
        segment_created_at=CREATED,
        segment_updated_at=CREATED,
        owner_segment_id=None,
        owner_status=None,
        owner_phase=None,
        owner_boot_id=None,
        owner_id=None,
        owner_created_at=None,
        owner_phase_updated_at=None,
        owner_closed_at=None,
        recovery_reason=None,
        observation_status=None,
        terminal_state_version=None,
        cause_phase=None,
        cause_code=None,
        recorded_at=None,
        initial_segment_count=1,
    )


def _family(family: LifecycleFamily) -> RecoveryLifecycleSnapshot:
    pending = _initial_pending()
    if family is LifecycleFamily.INITIAL_PENDING:
        return pending
    if family is LifecycleFamily.RETRY_PENDING:
        return replace(
            pending,
            attempt_count=1,
            last_error_code="run_dispatch_schedule_failed",
            dispatch_updated_at=STARTED,
        )
    if family is LifecycleFamily.LEASED:
        return replace(
            pending,
            dispatch_status="leased",
            lease_owner=WORKER_ID,
            lease_expires_at=TERMINAL,
            attempt_count=1,
            dispatch_updated_at=STARTED,
        )
    if family in {
        LifecycleFamily.RUNNING_EXECUTION,
        LifecycleFamily.RUNNING_FINALIZATION,
    }:
        return replace(
            pending,
            dispatch_status="started",
            attempt_count=1,
            dispatch_updated_at=STARTED,
            started_at=STARTED,
            execution_status="running",
            state_version=1,
            run_updated_at=STARTED,
            segment_status="running",
            segment_updated_at=STARTED,
            owner_segment_id=pending.segment_id,
            owner_status="active",
            owner_phase=(
                "execution"
                if family is LifecycleFamily.RUNNING_EXECUTION
                else "finalization"
            ),
            owner_boot_id=BOOT_ID,
            owner_id=OWNER_ID,
            owner_created_at=STARTED,
            owner_phase_updated_at=STARTED,
        )
    if family is LifecycleFamily.PRESTART_FAILED:
        return replace(
            pending,
            execution_status="failed",
            delivery_status="failed",
            state_version=1,
            run_updated_at=TERMINAL,
            segment_status="failed",
            segment_updated_at=TERMINAL,
            observation_status="observed",
            terminal_state_version=1,
            cause_phase="execution",
            cause_code="cancelled",
            recorded_at=TERMINAL,
        )
    if family is LifecycleFamily.DISPATCH_EXHAUSTED:
        return replace(
            pending,
            dispatch_status="failed",
            attempt_count=3,
            last_error_code="run_dispatch_schedule_failed",
            dispatch_updated_at=TERMINAL,
            execution_status="failed",
            delivery_status="failed",
            state_version=1,
            run_updated_at=TERMINAL,
            segment_status="failed",
            segment_updated_at=TERMINAL,
            observation_status="observed",
            terminal_state_version=1,
            cause_phase="dispatch",
            cause_code="run_dispatch_schedule_failed",
            recorded_at=TERMINAL,
        )
    if family is LifecycleFamily.CLOSED_TERMINAL:
        running = _family(LifecycleFamily.RUNNING_FINALIZATION)
        return replace(
            running,
            execution_status="completed",
            delivery_status="ready",
            state_version=2,
            run_updated_at=TERMINAL,
            segment_status="completed",
            segment_updated_at=TERMINAL,
            owner_status="closed",
            owner_boot_id=None,
            owner_id=None,
            owner_phase_updated_at=TERMINAL,
            owner_closed_at=TERMINAL,
        )
    if family is LifecycleFamily.LATER_BOOT_INTERRUPTED:
        running = _family(LifecycleFamily.RUNNING_EXECUTION)
        return replace(
            running,
            execution_status="failed",
            delivery_status="failed",
            state_version=2,
            run_updated_at=TERMINAL,
            segment_status="failed",
            segment_updated_at=TERMINAL,
            owner_status="interrupted",
            owner_boot_id=None,
            owner_id=None,
            owner_phase_updated_at=TERMINAL,
            owner_closed_at=TERMINAL,
            recovery_reason="previous_boot_interrupted",
            observation_status="observed",
            terminal_state_version=2,
            cause_phase="execution",
            cause_code="execution_error",
            recorded_at=TERMINAL,
        )
    raise AssertionError(f"unsupported family: {family}")


def _classify(
    snapshot: RecoveryLifecycleSnapshot,
    *,
    role: LifecycleRole = LifecycleRole.RECOVERY_REPLACEMENT,
) -> LifecycleFamily:
    return classify_recovery_lifecycle(
        snapshot,
        role=role,
        current_boot_id=BOOT_ID,
    )


def _assert_invalid(
    snapshot: RecoveryLifecycleSnapshot,
    *,
    role: LifecycleRole = LifecycleRole.RECOVERY_REPLACEMENT,
) -> None:
    with pytest.raises(
        LifecycleStateInvalid,
        match="^lifecycle_state_invalid$",
    ):
        _classify(snapshot, role=role)


def test_closed_role_and_family_values_are_exact():
    assert {value.value for value in LifecycleRole} == EXPECTED_ROLES
    assert {value.value for value in LifecycleFamily} == EXPECTED_FAMILIES


def test_classifier_has_no_registration_callback_or_io_surface():
    signature = inspect.signature(classify_recovery_lifecycle)
    assert tuple(signature.parameters) == ("snapshot", "role", "current_boot_id")
    assert not any(
        name.startswith(("register", "append", "replace", "load", "open"))
        for name in dir(inspect.getmodule(classify_recovery_lifecycle))
    )


@pytest.mark.parametrize(
    "family",
    [
        LifecycleFamily.INITIAL_PENDING,
        LifecycleFamily.RETRY_PENDING,
        LifecycleFamily.LEASED,
        LifecycleFamily.RUNNING_EXECUTION,
        LifecycleFamily.RUNNING_FINALIZATION,
        LifecycleFamily.PRESTART_FAILED,
        LifecycleFamily.DISPATCH_EXHAUSTED,
        LifecycleFamily.CLOSED_TERMINAL,
        LifecycleFamily.LATER_BOOT_INTERRUPTED,
    ],
)
def test_each_recovery_family_has_exactly_one_match(family):
    assert _classify(_family(family)) is family


def test_recovery_source_requires_exact_later_boot_interrupted_family():
    interrupted = _family(LifecycleFamily.LATER_BOOT_INTERRUPTED)
    assert (
        _classify(interrupted, role=LifecycleRole.RECOVERY_SOURCE)
        is LifecycleFamily.LATER_BOOT_INTERRUPTED
    )
    _assert_invalid(
        _family(LifecycleFamily.CLOSED_TERMINAL),
        role=LifecycleRole.RECOVERY_SOURCE,
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("execution_status", "completed"),
        ("segment_status", "completed"),
        ("dispatch_status", "started"),
        ("owner_status", "closed"),
        ("observation_status", "observed"),
        ("owner_boot_id", f"boot_{'e' * 32}"),
        ("run_updated_at", TERMINAL),
        ("initial_segment_count", 2),
    ],
)
def test_each_authority_field_mutation_rejects_or_becomes_named_family(
    field_name,
    invalid_value,
):
    snapshot = replace(_initial_pending(), **{field_name: invalid_value})
    _assert_invalid(snapshot)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (LifecycleFamily.INITIAL_PENDING, LifecycleFamily.CLOSED_TERMINAL),
        (LifecycleFamily.LEASED, LifecycleFamily.RUNNING_EXECUTION),
        (LifecycleFamily.RUNNING_EXECUTION, LifecycleFamily.DISPATCH_EXHAUSTED),
        (LifecycleFamily.CLOSED_TERMINAL, LifecycleFamily.LATER_BOOT_INTERRUPTED),
    ],
)
def test_pairwise_cross_family_group_substitutions_reject(left, right):
    left_snapshot = _family(left)
    right_snapshot = _family(right)
    mixed = replace(
        left_snapshot,
        execution_status=right_snapshot.execution_status,
        state_version=right_snapshot.state_version,
        segment_status=right_snapshot.segment_status,
    )
    _assert_invalid(mixed)


def test_first_lease_rejects_prior_error():
    _assert_invalid(
        replace(
            _family(LifecycleFamily.LEASED),
            last_error_code="run_dispatch_schedule_failed",
        )
    )


@pytest.mark.parametrize(
    "last_error_code",
    [None, "run_dispatch_schedule_failed"],
)
def test_reclaimed_later_lease_allows_absent_or_bounded_prior_error(
    last_error_code,
):
    reclaimed = replace(
        _family(LifecycleFamily.LEASED),
        attempt_count=2,
        last_error_code=last_error_code,
    )
    assert _classify(reclaimed) is LifecycleFamily.LEASED


def test_ordinary_compatibility_cannot_authorize_replacement():
    ordinary_terminal = replace(
        _initial_pending(),
        execution_status="completed",
        delivery_status="ready",
        state_version=1,
        run_updated_at=TERMINAL,
        segment_status="completed",
        segment_updated_at=TERMINAL,
    )
    assert (
        _classify(ordinary_terminal, role=LifecycleRole.ORDINARY)
        is LifecycleFamily.ORDINARY_COMPATIBLE
    )
    _assert_invalid(ordinary_terminal)


def test_ordinary_review_required_terminal_compatibility_remains_retained():
    ordinary_review = replace(
        _initial_pending(),
        execution_status="completed",
        review_status="required",
        delivery_status="review_required",
        state_version=1,
        segment_status="completed",
    )
    assert (
        _classify(ordinary_review, role=LifecycleRole.ORDINARY)
        is LifecycleFamily.ORDINARY_COMPATIBLE
    )
    _assert_invalid(ordinary_review)


def test_ordinary_legacy_ownerless_pending_dispatch_compatibility_is_closed():
    legacy = replace(
        _initial_pending(),
        execution_status="completed",
        delivery_status="ready",
        segment_status="completed",
    )
    assert (
        _classify(legacy, role=LifecycleRole.ORDINARY)
        is LifecycleFamily.ORDINARY_COMPATIBLE
    )
    _assert_invalid(legacy)


def test_closed_failure_retains_existing_cause_phase_mapping():
    closed = _family(LifecycleFamily.CLOSED_TERMINAL)
    failed = replace(
        closed,
        execution_status="failed",
        delivery_status="failed",
        segment_status="failed",
        cause_phase="execution",
        cause_code="call_budget_exceeded",
        observation_status="observed",
        terminal_state_version=2,
        recorded_at=TERMINAL,
    )
    assert _classify(failed) is LifecycleFamily.CLOSED_TERMINAL


def test_closed_terminal_retains_required_review_delivery_pair():
    closed = replace(
        _family(LifecycleFamily.CLOSED_TERMINAL),
        review_status="required",
        delivery_status="review_required",
    )
    assert _classify(closed) is LifecycleFamily.CLOSED_TERMINAL


def test_closed_terminal_retains_later_review_state_version():
    closed = replace(
        _family(LifecycleFamily.CLOSED_TERMINAL),
        review_status="resolved",
        delivery_status="ready",
        state_version=3,
        run_updated_at="2026-07-29T00:03:00+00:00",
    )
    assert _classify(closed) is LifecycleFamily.CLOSED_TERMINAL


def test_snapshot_fields_are_the_complete_closed_projection():
    assert {field.name for field in fields(RecoveryLifecycleSnapshot)} == {
        "run_id",
        "dispatch_status",
        "lease_owner",
        "lease_expires_at",
        "attempt_count",
        "last_error_code",
        "dispatch_created_at",
        "dispatch_updated_at",
        "started_at",
        "execution_status",
        "review_status",
        "delivery_status",
        "state_version",
        "run_created_at",
        "run_updated_at",
        "segment_id",
        "segment_run_id",
        "kind",
        "sequence",
        "segment_attempt",
        "segment_status",
        "segment_created_at",
        "segment_updated_at",
        "owner_segment_id",
        "owner_status",
        "owner_phase",
        "owner_boot_id",
        "owner_id",
        "owner_created_at",
        "owner_phase_updated_at",
        "owner_closed_at",
        "recovery_reason",
        "observation_status",
        "terminal_state_version",
        "cause_phase",
        "cause_code",
        "recorded_at",
        "initial_segment_count",
    }
