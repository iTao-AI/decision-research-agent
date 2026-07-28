from __future__ import annotations

import json
import math
import re
import stat
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = (
    PROJECT_ROOT / "benchmarks/evidence-gated-loop-v1/registry.json"
)
CASES_ROOT = REGISTRY_PATH.parent / "cases"
MAX_REGISTRY_BYTES = 65536
MAX_CASE_BYTES = 262144
MAX_REPORT_BYTES = 2097152
MAX_TEXT_BYTES = 8192
MAX_COLLECTION_ITEMS = 256
MAX_DEPTH = 16
REQUIRED_NON_CLAIMS = (
    "No runtime self-modification, automatic diagnosis, candidate "
    "generation, promotion, release, or rollback.",
    "No live-provider success, production reliability, user-adoption, "
    "business-impact, or universal Agent-quality claim.",
    "Current fixed profiles verify retained repository state; they do not "
    "check out arbitrary historical candidates or infer human verdicts.",
    "The v0.1.6 selector verifies current release metadata only; it does "
    "not execute historical release behavior.",
    "Post-v0.1.6 capabilities are not part of the immutable v0.1.6 release.",
)

_FORBIDDEN_KEYS = frozenset(
    {
        "prompt",
        "query",
        "snippet",
        "tool_payload",
        "provider_payload",
        "exception",
        "traceback",
        "credential",
        "password",
        "secret",
        "token",
        "thread_id",
        "source_thread_id",
    }
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[=:]\s*\S+"
)
_WINDOWS_PATH_RE = re.compile(r"(?:^|[\s(])(?:[A-Za-z]:\\|\\\\)[^\s]+")
ABSOLUTE_POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:/])/[A-Za-z0-9._~%+-]+"
    r"(?:/[A-Za-z0-9._~%+-]+)*"
    r"(?=$|[\s,.;:)\]}'\"])",
)


class LoopBoundedReadError(ValueError):
    pass


class LoopContractError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


Identifier = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
]
PublicText = Annotated[str, StringConstraints(min_length=1, max_length=8192)]


class VerificationProfileRef(_StrictModel):
    profile_id: Identifier
    profile_version: Identifier


class RegistryLimits(_StrictModel):
    max_case_bytes: Literal[262144]
    max_case_count: Literal[32]
    max_collection_items: Literal[256]
    max_depth: Literal[16]
    max_registry_bytes: Literal[65536]
    max_report_bytes: Literal[2097152]
    max_text_bytes: Literal[8192]


class LoopRegistry(_StrictModel):
    schema_version: Literal["dra.evidence-gated-loop-registry.v1"]
    kernel_id: Literal["dra.evidence-gated-loop-kernel"]
    kernel_version: Literal["1"]
    case_paths: list[str] = Field(min_length=1, max_length=32)
    verification_profiles: list[VerificationProfileRef] = Field(
        min_length=1, max_length=16
    )
    limits: RegistryLimits
    non_claims: list[PublicText] = Field(min_length=3, max_length=16)

    @model_validator(mode="after")
    def _closed_ordered_registry(self) -> "LoopRegistry":
        if self.case_paths != sorted(set(self.case_paths)):
            raise ValueError("case path order")
        path_pattern = re.compile(
            r"^benchmarks/evidence-gated-loop-v1/cases/"
            r"[a-z0-9][a-z0-9._-]{0,127}\.json$"
        )
        if any(
            path_pattern.fullmatch(path) is None
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            for path in self.case_paths
        ):
            raise ValueError("case path")
        identities = [
            (item.profile_id, item.profile_version)
            for item in self.verification_profiles
        ]
        if identities != sorted(set(identities)):
            raise ValueError("profile order")
        if tuple(self.non_claims) != REQUIRED_NON_CLAIMS:
            raise ValueError("non-claims")
        return self


def read_bounded_bytes(path: Path, *, limit: int) -> bytes:
    try:
        if path.is_symlink():
            raise LoopBoundedReadError("symlink")
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise LoopBoundedReadError("not regular")
        with path.open("rb") as handle:
            value = handle.read(limit + 1)
    except (OSError, LoopBoundedReadError) as exc:
        raise LoopBoundedReadError("bounded read") from exc
    if len(value) > limit:
        raise LoopBoundedReadError("oversized")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise LoopContractError("loop_public_output_unsafe") from exc


def validate_public_projection(value: Any) -> Any:
    def visit(item: Any, *, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise LoopContractError("loop_public_output_unsafe")
        if item is None or isinstance(item, bool) or isinstance(item, int):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise LoopContractError("loop_public_output_unsafe")
            return
        if isinstance(item, str):
            if len(item.encode("utf-8")) > MAX_TEXT_BYTES:
                raise LoopContractError("loop_public_output_unsafe")
            if any(ord(char) < 32 for char in item):
                raise LoopContractError("loop_public_output_unsafe")
            if (
                "Traceback" in item
                or ABSOLUTE_POSIX_PATH_RE.search(item)
                or _WINDOWS_PATH_RE.search(item)
                or _CREDENTIAL_ASSIGNMENT_RE.search(item)
            ):
                raise LoopContractError("loop_public_output_unsafe")
            return
        if isinstance(item, list):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise LoopContractError("loop_public_output_unsafe")
            for child in item:
                visit(child, depth=depth + 1)
            return
        if isinstance(item, dict):
            if len(item) > MAX_COLLECTION_ITEMS:
                raise LoopContractError("loop_public_output_unsafe")
            for key, child in item.items():
                if not isinstance(key, str):
                    raise LoopContractError("loop_public_output_unsafe")
                normalized = key.lower().replace("-", "_")
                if normalized in _FORBIDDEN_KEYS:
                    raise LoopContractError("loop_public_output_unsafe")
                visit(key, depth=depth + 1)
                visit(child, depth=depth + 1)
            return
        raise LoopContractError("loop_public_output_unsafe")

    visit(value, depth=0)
    return value


def validate_registry(value: Mapping[str, Any]) -> LoopRegistry:
    try:
        validate_public_projection(value)
        return LoopRegistry.model_validate(value, strict=True)
    except (ValidationError, LoopContractError, ValueError, TypeError) as exc:
        raise LoopContractError("loop_registry_invalid") from exc


def load_registry(path: Path = REGISTRY_PATH) -> LoopRegistry:
    try:
        raw = read_bounded_bytes(path, limit=MAX_REGISTRY_BYTES)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("registry")
        registry = validate_registry(value)
        if raw != canonical_json_bytes(registry):
            raise ValueError("canonical")
        return registry
    except (LoopBoundedReadError, LoopContractError, ValueError, TypeError) as exc:
        raise LoopContractError("loop_registry_invalid") from exc
