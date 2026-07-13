import pytest

from api.run_creation_models import (
    RUN_CREATE_REQUEST_SCHEMA_VERSION,
    RunCreationAcceptance,
    idempotency_key_hash,
    run_create_request_hash,
    validate_idempotency_key,
)


@pytest.mark.parametrize(
    "value",
    [
        "12345678",
        "run-create-12345678",
        "A.b_c:d-12345678",
        "a" * 128,
    ],
)
def test_idempotency_key_accepts_exact_public_contract(value):
    assert validate_idempotency_key(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "1234567",
        "a" * 129,
        " leading-key",
        "trailing-key ",
        "line\nbreak",
        "trailing-newline\n",
        "control\x00key",
        "unicode-key-测试",
        "slash/key",
    ],
)
def test_idempotency_key_rejects_out_of_contract_values(value):
    with pytest.raises(ValueError, match="run_idempotency_key_invalid"):
        validate_idempotency_key(value)


def test_key_hash_is_namespaced_stable_and_does_not_contain_raw_key():
    raw = "run-create-12345678"
    first = idempotency_key_hash(raw)
    second = idempotency_key_hash(raw)
    assert first == second
    assert len(first) == 64
    assert raw not in first
    assert first != idempotency_key_hash("run-create-87654321")


def test_request_hash_is_canonical_for_scope_key_order():
    first = run_create_request_hash(
        query="bounded query",
        thread_id=None,
        profile_id="generic",
        scope={"b": 2, "a": {"d": 4, "c": 3}},
    )
    second = run_create_request_hash(
        query="bounded query",
        thread_id=None,
        profile_id="generic",
        scope={"a": {"c": 3, "d": 4}, "b": 2},
    )
    assert first == second


def test_request_hash_preserves_caller_thread_intent_and_request_content():
    base = dict(query="query", profile_id="generic", scope={})
    omitted = run_create_request_hash(thread_id=None, **base)
    explicit = run_create_request_hash(thread_id="thread-1", **base)
    changed_query = run_create_request_hash(
        thread_id=None,
        query="query ",
        profile_id="generic",
        scope={},
    )
    assert omitted != explicit
    assert omitted != changed_query


def test_acceptance_is_strict_and_json_serializable():
    value = RunCreationAcceptance(
        run_id="run_1",
        thread_id="thread_1",
        segment_id="run_1_seg_000",
        idempotent_replay=False,
    )
    assert value.model_dump(mode="json") == {
        "run_id": "run_1",
        "thread_id": "thread_1",
        "segment_id": "run_1_seg_000",
        "idempotent_replay": False,
    }
    assert RUN_CREATE_REQUEST_SCHEMA_VERSION == "dra.run-create-request.v1"
