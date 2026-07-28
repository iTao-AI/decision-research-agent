from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evidence_gated_loop_contracts import (
    MAX_COLLECTION_ITEMS,
    MAX_DEPTH,
    MAX_REGISTRY_BYTES,
    PROJECT_ROOT,
    LoopContractError,
    canonical_json_bytes,
    load_registry,
    validate_public_projection,
    validate_registry,
)


REGISTRY_PATH = (
    PROJECT_ROOT / "benchmarks/evidence-gated-loop-v1/registry.json"
)


def _registry_value() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_accepts_exact_closed_provider_free_contract() -> None:
    registry = load_registry()
    assert registry.schema_version == "dra.evidence-gated-loop-registry.v1"
    assert registry.kernel_id == "dra.evidence-gated-loop-kernel"
    assert [ref.profile_id for ref in registry.verification_profiles] == [
        "context-resolver-coherence",
        "evaluation-sensitivity",
        "strict-citation-consumer",
    ]
    assert list(registry.case_paths) == sorted(registry.case_paths)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.__setitem__("extra", True), "loop_registry_invalid"),
        (
            lambda value: value["case_paths"].append(value["case_paths"][0]),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"].append(
                dict(value["verification_profiles"][0])
            ),
            "loop_registry_invalid",
        ),
        (lambda value: value["case_paths"].reverse(), "loop_registry_invalid"),
        (
            lambda value: value["case_paths"].__setitem__(0, "../escape.json"),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["case_paths"].__setitem__(
                0,
                "benchmarks/evidence-gated-loop-v1/cases/nested/case.json",
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "command", ["pytest"]
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "selector", "tests/unit/test_private.py"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "import_path", "private.module"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "environment", {"TOKEN": "value"}
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["verification_profiles"][0].__setitem__(
                "output_path", "/tmp/report"
            ),
            "loop_registry_invalid",
        ),
        (
            lambda value: value["non_claims"].__setitem__(
                0, "No additional boundary."
            ),
            "loop_registry_invalid",
        ),
    ],
)
def test_registry_rejects_schema_order_path_and_executable_surface_mutations(
    mutation, code
) -> None:
    value = _registry_value()
    mutation(value)
    with pytest.raises(LoopContractError, match=code):
        validate_registry(value)


def test_bounded_read_stops_at_limit_plus_one(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b"x" * (MAX_REGISTRY_BYTES + 1))
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)


def test_registry_requires_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    value = _registry_value()
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(path)


def test_registry_symlink_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(canonical_json_bytes(_registry_value()))
    link = tmp_path / "registry.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(LoopContractError, match="loop_registry_invalid"):
        load_registry(link)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"items": list(range(MAX_COLLECTION_ITEMS + 1))},
        {"number": float("nan")},
    ],
)
def test_public_projection_rejects_excessive_or_nonfinite_values(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)


def test_public_projection_rejects_excessive_depth() -> None:
    unsafe: dict[str, object] = {}
    cursor = unsafe
    for index in range(MAX_DEPTH + 1):
        child: dict[str, object] = {}
        cursor[f"level_{index}"] = child
        cursor = child
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"prompt": "body"},
        {"safe": "Traceback: private"},
        {"safe": "/Users/private/repo"},
        {"safe": "saved under /private/runtime/report.json"},
        {"safe": "saved under /var/tmp/report.json"},
        {"safe": "saved under /tmp/report.json"},
        {"safe": "saved under /Volumes/work/report.json"},
        {"safe": "saved under /opt/service/report.json"},
        {"safe": "saved under /etc/service/report.json"},
        {"safe": "saved under /root/report.json"},
        {"safe": "api_key=secret"},
        {"tool_payload": {"value": "body"}},
    ],
)
def test_public_projection_rejects_body_path_trace_and_credentials(
    unsafe: object,
) -> None:
    with pytest.raises(LoopContractError, match="loop_public_output_unsafe"):
        validate_public_projection(unsafe)
