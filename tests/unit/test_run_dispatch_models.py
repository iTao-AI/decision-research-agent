from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.run_dispatch_models import (
    MAX_RUN_DISPATCH_ATTEMPTS,
    RUN_DISPATCH_MIGRATION_CHECKSUM,
    RUN_DISPATCH_MIGRATION_VERSION,
    RUN_DISPATCH_STATUSES,
    RunDispatchClaim,
    RunDispatchConflict,
)


def _valid_claim():
    return {
        "run_id": "run_0001",
        "thread_id": "thread-1",
        "segment_id": "run_0001_seg_000",
        "query": "research",
        "profile_id": "generic",
        "profile_version": "1",
        "scope_json": "{}",
        "lease_owner": "dispatch_worker_00000000000000000000000000000001",
        "attempt_count": 1,
        "lease_expires_at": datetime(2026, 7, 14, tzinfo=timezone.utc),
    }


def test_dispatch_constants():
    assert RUN_DISPATCH_MIGRATION_VERSION == "008_run_dispatch_reconciliation"
    assert RUN_DISPATCH_MIGRATION_CHECKSUM == "run-dispatch-reconciliation-v1"
    assert RUN_DISPATCH_STATUSES == frozenset(
        {"pending", "leased", "started", "failed"}
    )
    assert MAX_RUN_DISPATCH_ATTEMPTS == 3


def test_claim_is_strict_frozen_and_forbids_extra():
    claim = RunDispatchClaim.model_validate(_valid_claim(), strict=True)
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate(
            {**_valid_claim(), "attempt_count": "1"}, strict=True
        )
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate(
            {**_valid_claim(), "unexpected": True}, strict=True
        )
    with pytest.raises(ValidationError):
        claim.attempt_count = 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", ""),
        ("thread_id", ""),
        ("segment_id", ""),
        ("profile_id", ""),
        ("profile_version", ""),
        ("lease_owner", "caller_worker_00000000000000000000000000000001"),
        ("lease_owner", "dispatch_worker_not-hex"),
        ("attempt_count", 0),
        ("lease_expires_at", datetime(2026, 7, 14)),
    ],
)
def test_claim_rejects_invalid_bounded_fields(field, value):
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate(
            {**_valid_claim(), field: value}, strict=True
        )


@pytest.mark.parametrize(
    "scope_json",
    [
        "[]",
        "null",
        "not-json",
        '{"b":2, "a":1}',
        '{"b":2,"a":1}',
        '{"a": 1}',
    ],
)
def test_claim_rejects_non_object_invalid_or_noncanonical_scope(scope_json):
    with pytest.raises(ValidationError):
        RunDispatchClaim.model_validate(
            {**_valid_claim(), "scope_json": scope_json}, strict=True
        )


def test_claim_scope_returns_a_fresh_mapping():
    claim = RunDispatchClaim.model_validate(
        {**_valid_claim(), "scope_json": '{"filters":{"region":"cn"}}'},
        strict=True,
    )
    first = claim.scope
    first["filters"]["region"] = "changed"

    assert claim.scope_json == '{"filters":{"region":"cn"}}'
    assert claim.scope == {"filters": {"region": "cn"}}


def test_dispatch_conflict_exposes_only_stable_code():
    conflict = RunDispatchConflict("run_dispatch_unavailable")
    assert conflict.code == "run_dispatch_unavailable"
    assert str(conflict) == "run_dispatch_unavailable"
