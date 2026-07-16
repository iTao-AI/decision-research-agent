import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from api.run_failure_cause_models import (
    RUN_FAILURE_CAUSE_CODES,
    RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM,
    RUN_FAILURE_CAUSE_MIGRATION_VERSION,
    RUN_FAILURE_CAUSE_SCHEMA_VERSION,
    NotObservedRunFailureCause,
    ObservedRunFailureCause,
    RunFailureCauseConflict,
    RunFailureCauseProjectionAdapter,
    RunFailureCauseWrite,
    RunStatusFailureCauseOpenAPI,
)


EXPECTED = {
    "dispatch": {
        "run_dispatch_schedule_failed",
        "run_dispatch_start_failed",
        "run_dispatch_start_timeout",
        "run_dispatch_lease_expired",
    },
    "execution": {
        "call_budget_exceeded",
        "recursion_limit_exceeded",
        "invalid_research_packet",
        "missing_research_packet",
        "run_timeout",
        "cancelled",
        "execution_error",
    },
    "finalization": {
        "run_timeout",
        "cancelled",
        "run_finalization_failed",
    },
}

VALID_PAIRS = [
    (phase, code)
    for phase, codes in EXPECTED.items()
    for code in sorted(codes)
]
ALL_CODES = set().union(*EXPECTED.values())
INVALID_CROSS_PHASE_PAIRS = [
    (phase, code)
    for phase, allowed_codes in EXPECTED.items()
    for code in sorted(ALL_CODES - allowed_codes)
]


def test_failure_cause_constants_and_matrix_are_exact_and_immutable():
    assert RUN_FAILURE_CAUSE_SCHEMA_VERSION == "dra.run-failure-cause.v1"
    assert RUN_FAILURE_CAUSE_MIGRATION_VERSION == "009_run_failure_cause_v1"
    assert RUN_FAILURE_CAUSE_MIGRATION_CHECKSUM == "run-failure-cause-v1"
    assert {
        key: set(value) for key, value in RUN_FAILURE_CAUSE_CODES.items()
    } == EXPECTED

    with pytest.raises(TypeError):
        RUN_FAILURE_CAUSE_CODES["execution"] = frozenset()
    with pytest.raises(AttributeError):
        RUN_FAILURE_CAUSE_CODES["execution"].add("new_code")


@pytest.mark.parametrize(("phase", "code"), VALID_PAIRS)
def test_write_contract_accepts_only_exact_phase_code_pairs(phase, code):
    value = RunFailureCauseWrite.model_validate(
        {"phase": phase, "code": code}, strict=True
    )

    assert value.phase == phase
    assert value.code == code


@pytest.mark.parametrize(("phase", "code"), INVALID_CROSS_PHASE_PAIRS)
def test_write_contract_rejects_every_cross_phase_mismatch(phase, code):
    with pytest.raises(ValidationError, match="run_failure_cause_invalid"):
        RunFailureCauseWrite.model_validate(
            {"phase": phase, "code": code}, strict=True
        )


def test_write_contract_rejects_unknown_codes_extra_fields_and_coercion():
    invalid_payloads = [
        {"phase": "execution", "code": "provider_rate_limit"},
        {
            "phase": "execution",
            "code": "execution_error",
            "error_message": "RuntimeError: provider secret at /private/tasks.db",
        },
        {"phase": "execution", "code": 1},
        {"phase": 1, "code": "execution_error"},
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            RunFailureCauseWrite.model_validate(payload, strict=True)


def test_write_contract_is_frozen():
    value = RunFailureCauseWrite(
        phase="execution",
        code="execution_error",
    )

    with pytest.raises(ValidationError, match="frozen_instance"):
        value.code = "call_budget_exceeded"


def test_projection_variants_are_strict_and_historical_has_no_inference():
    recorded_at = datetime(2026, 7, 16, tzinfo=timezone.utc)
    observed = ObservedRunFailureCause.model_validate(
        {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "observed",
            "phase": "execution",
            "code": "execution_error",
            "recorded_at": recorded_at,
        },
        strict=True,
    )
    historical = NotObservedRunFailureCause.model_validate(
        {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "not_observed",
        },
        strict=True,
    )

    assert observed.recorded_at.utcoffset() == timedelta(0)
    assert historical.model_dump(mode="json") == {
        "schema_version": "dra.run-failure-cause.v1",
        "observation_status": "not_observed",
    }
    with pytest.raises(ValidationError):
        NotObservedRunFailureCause.model_validate(
            {
                "schema_version": "dra.run-failure-cause.v1",
                "observation_status": "not_observed",
                "phase": "execution",
            },
            strict=True,
        )


@pytest.mark.parametrize(
    "recorded_at",
    [
        datetime(2026, 7, 16),
        datetime(2026, 7, 16, tzinfo=timezone(timedelta(hours=8))),
        "2026-07-16T00:00:00+00:00",
    ],
)
def test_observed_projection_rejects_naive_non_utc_and_coerced_time(recorded_at):
    with pytest.raises(ValidationError):
        ObservedRunFailureCause.model_validate(
            {
                "schema_version": "dra.run-failure-cause.v1",
                "observation_status": "observed",
                "phase": "execution",
                "code": "execution_error",
                "recorded_at": recorded_at,
            },
            strict=True,
        )


def test_projection_adapter_is_discriminated_and_strict():
    historical = RunFailureCauseProjectionAdapter.validate_python(
        {
            "schema_version": "dra.run-failure-cause.v1",
            "observation_status": "not_observed",
        },
        strict=True,
    )
    assert isinstance(historical, NotObservedRunFailureCause)

    with pytest.raises(ValidationError):
        RunFailureCauseProjectionAdapter.validate_python(
            {
                "schema_version": "dra.run-failure-cause.v1",
                "observation_status": "unknown",
            },
            strict=True,
        )


def test_status_openapi_declares_only_required_nullable_discriminated_field():
    schema = RunStatusFailureCauseOpenAPI.model_json_schema()
    field_schema = schema["properties"]["failure_cause"]
    nullable_variants = field_schema["anyOf"]
    cause_union = next(
        variant for variant in nullable_variants if "discriminator" in variant
    )

    assert schema["required"] == ["failure_cause"]
    assert set(schema["properties"]) == {"failure_cause"}
    assert schema["additionalProperties"] is True
    assert any(variant.get("type") == "null" for variant in nullable_variants)
    assert cause_union["discriminator"]["propertyName"] == "observation_status"
    assert len(cause_union["oneOf"]) == 2
    assert "terminal_state_version" not in json.dumps(schema, sort_keys=True)


def test_conflict_exposes_only_the_bounded_code():
    conflict = RunFailureCauseConflict("run_failure_cause_corrupt")

    assert conflict.code == "run_failure_cause_corrupt"
    assert str(conflict) == "run_failure_cause_corrupt"
