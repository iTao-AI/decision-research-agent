import pytest
from pydantic import ValidationError

from api.run_creation_models import idempotency_key_hash
from api.run_recovery_models import (
    RunRecoveryAcceptance,
    RunRecoveryConflict,
    recovery_key_hash,
    run_recovery_request_hash,
    validate_recovery_key,
)


def _acceptance(**overrides):
    values = {
        "schema_version": "dra.run-recovery.v1",
        "status": "accepted",
        "reason": "previous_boot_interrupted",
        "interrupted_phase": "execution",
        "source_run_id": "run_source",
        "run_id": "run_replacement",
        "thread_id": "caller-thread",
        "segment_id": "run_replacement_seg_000",
        "recovery_attempt": 1,
        "idempotent_replay": False,
    }
    values.update(overrides)
    return RunRecoveryAcceptance(**values)


def _fingerprint(**overrides):
    values = {
        "source_run_id": "run_source",
        "segment_id": "run_source_seg_000",
        "query": "query",
        "thread_id": "thread",
        "profile_id": "generic",
        "profile_version": "1",
        "scope": {"b": 2, "a": 1},
        "execution_status": "failed",
        "review_status": "not_required",
        "delivery_status": "failed",
        "terminal_state_version": 2,
        "failure_phase": "execution",
        "failure_code": "execution_error",
        "recovery_reason": "previous_boot_interrupted",
        "interrupted_phase": "execution",
        "recovery_attempt": 1,
    }
    values.update(overrides)
    return values


def test_recovery_acceptance_has_exact_ten_field_public_shape():
    assert set(_acceptance().model_dump(mode="json")) == {
        "schema_version", "status", "reason", "interrupted_phase",
        "source_run_id", "run_id", "thread_id", "segment_id",
        "recovery_attempt", "idempotent_replay",
    }


def test_recovery_acceptance_rejects_extra_fields_and_coercion():
    with pytest.raises(ValidationError):
        _acceptance(extra=True)
    with pytest.raises(ValidationError):
        _acceptance(idempotent_replay=0)


def test_recovery_acceptance_rejects_source_equal_replacement():
    with pytest.raises(ValidationError):
        _acceptance(run_id="run_source", segment_id="run_source_seg_000")


def test_recovery_acceptance_requires_exact_replacement_initial_segment():
    with pytest.raises(ValidationError):
        _acceptance(segment_id="segment_other")


@pytest.mark.parametrize("field,value", [("run_id", ""), ("source_run_id", ""), ("thread_id", ""), ("segment_id", ""), ("run_id", "x" * 129)])
def test_recovery_acceptance_rejects_empty_or_overlong_public_identities(field, value):
    with pytest.raises(ValidationError):
        _acceptance(**{field: value})


@pytest.mark.parametrize("value", [None, "short", "unicode-测试", " leading-key", "key with space", True])
def test_recovery_key_rejects_missing_short_unicode_whitespace_and_bool(value):
    with pytest.raises((ValueError, TypeError)):
        validate_recovery_key(value)


def test_recovery_key_hash_uses_a_distinct_namespace_and_never_contains_raw_key():
    raw = "recovery-key-1234"
    digest = recovery_key_hash(raw)
    assert len(digest) == 64
    assert raw not in digest
    assert digest != idempotency_key_hash(raw)


def test_request_hash_binds_every_immutable_source_and_terminal_field():
    base = run_recovery_request_hash(**_fingerprint())
    changes = {
        "source_run_id": "run_other",
        "segment_id": "run_other_seg_000",
        "query": "other query",
        "thread_id": "other-thread",
        "profile_id": "other-profile",
        "profile_version": "2",
        "scope": {"changed": True},
        "failure_phase": "finalization",
        "failure_code": "run_finalization_failed",
        "recovery_reason": "pre_v1_running_without_owner",
        "interrupted_phase": "finalization",
    }
    for field, changed in changes.items():
        assert run_recovery_request_hash(**_fingerprint(**{field: changed})) != base


def test_request_hash_is_canonical_for_scope_key_order_only():
    assert run_recovery_request_hash(**_fingerprint(scope={"a": 1, "b": 2})) == run_recovery_request_hash(**_fingerprint(scope={"b": 2, "a": 1}))


@pytest.mark.parametrize("field,value", [("segment_id", "run_source_seg_001"), ("profile_version", "2"), ("failure_code", "other"), ("recovery_reason", "pre_v1_running_without_owner")])
def test_request_hash_changes_for_segment_profile_state_cause_owner_or_attempt_drift(field, value):
    assert run_recovery_request_hash(**_fingerprint(**{field: value})) != run_recovery_request_hash(**_fingerprint())
    for invalid_field, invalid_value in (("terminal_state_version", 1), ("recovery_attempt", 2)):
        with pytest.raises((ValidationError, ValueError)):
            run_recovery_request_hash(**_fingerprint(**{invalid_field: invalid_value}))


def test_recovery_conflict_contains_only_a_bounded_code():
    exc = RunRecoveryConflict("run_recovery_conflict")
    assert exc.code == "run_recovery_conflict"
    assert str(exc) == exc.code
