from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from api.run_execution_models import (
    RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM,
    RUN_EXECUTION_RECOVERY_MIGRATION_VERSION,
    RUN_EXECUTION_PHASES,
    RUN_EXECUTION_RECOVERY_REASONS,
    RUN_EXECUTION_OWNER_STATUSES,
    RunExecutionConflict,
    RunExecutionOwnerBox,
    RunExecutionOwnerHandle,
)


def _handle(**overrides):
    values = {
        "run_id": "run_source",
        "segment_id": "run_source_seg_000",
        "boot_id": f"boot_{'a' * 32}",
        "owner_id": f"owner_{'b' * 32}",
    }
    values.update(overrides)
    return RunExecutionOwnerHandle(**values)


def test_execution_constants_are_closed_and_have_no_lease_expiry():
    import api.run_execution_models as models

    assert RUN_EXECUTION_RECOVERY_MIGRATION_VERSION == "010_run_execution_recovery"
    assert RUN_EXECUTION_RECOVERY_MIGRATION_CHECKSUM == "run-execution-recovery-v1"
    assert RUN_EXECUTION_OWNER_STATUSES == frozenset({"active", "closed", "interrupted"})
    assert RUN_EXECUTION_PHASES == frozenset({"execution", "finalization"})
    assert RUN_EXECUTION_RECOVERY_REASONS == frozenset(
        {"previous_boot_interrupted", "pre_v1_running_without_owner"}
    )
    assert not any(
        token in name.lower()
        for name in dir(models)
        for token in ("heartbeat", "lease_duration", "expiry_threshold", "scan_interval", "automatic_retry")
    )


def test_owner_handle_is_strict_frozen_and_private_identity_bounded():
    handle = _handle()
    with pytest.raises(ValidationError):
        handle.run_id = "changed"
    with pytest.raises(ValidationError):
        _handle(extra="forbidden")


@pytest.mark.parametrize(
    "field,value",
    [
        ("boot_id", f"owner_{'a' * 32}"),
        ("boot_id", "boot_"),
        ("owner_id", f"boot_{'b' * 32}"),
        ("owner_id", "owner_Z"),
        ("run_id", ""),
        ("segment_id", ""),
        ("run_id", True),
    ],
)
def test_owner_handle_rejects_coercion_wrong_prefix_and_empty_identity(field, value):
    with pytest.raises(ValidationError):
        _handle(**{field: value})


def test_owner_box_is_empty_then_assigns_exactly_once():
    box = RunExecutionOwnerBox()
    assert box.get() is None
    handle = _handle()
    box.assign(handle)
    assert box.require() is handle
    with pytest.raises(RunExecutionConflict, match="run_execution_owner_already_assigned"):
        box.assign(handle)


def test_owner_box_is_thread_safe_and_never_replaces_winner():
    box = RunExecutionOwnerBox()
    handles = [_handle(owner_id=f"owner_{index:032x}") for index in range(16)]

    def assign(handle):
        try:
            box.assign(handle)
        except RunExecutionConflict:
            pass

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(assign, handles))
    assert box.require() in handles


def test_owner_box_returns_the_same_immutable_handle():
    box = RunExecutionOwnerBox()
    handle = _handle()
    box.assign(handle)
    assert box.get() is handle
    assert box.require() is handle


def test_execution_conflict_contains_only_a_bounded_code():
    exc = RunExecutionConflict("run_execution_owner_stale")
    assert exc.code == "run_execution_owner_stale"
    assert str(exc) == exc.code
