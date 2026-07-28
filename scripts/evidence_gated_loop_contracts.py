from __future__ import annotations

import json
import math
import re
import stat
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping
from urllib.parse import urlsplit

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


CommitSha = Annotated[
    str, StringConstraints(pattern=r"^[0-9a-f]{40}$")
]
Carrier = Literal[
    "knowledge", "prompt_skill", "program_harness", "model_parameters"
]
ChangeSurface = Literal[
    "knowledge",
    "prompt_skill",
    "runtime_harness",
    "evaluation_proof",
    "model_parameters",
]
ProofKind = Literal[
    "reviewed_historical_red",
    "reviewed_verification_gap",
    "reviewed_candidate_verification_passed",
    "independent_consumer_contract",
    "reviewed_candidate_regression",
    "reviewed_candidate_safety_failure",
    "reviewed_candidate_verification_inconclusive",
    "independent_consumer_rejection",
]
SUBJECT_REQUIRED_PROOF_KINDS = frozenset(
    {
        "reviewed_candidate_verification_passed",
        "independent_consumer_contract",
        "reviewed_candidate_regression",
        "reviewed_candidate_safety_failure",
        "reviewed_candidate_verification_inconclusive",
        "independent_consumer_rejection",
    }
)
ALLOWED_ORIGINS_BY_PROOF_KIND = {
    "reviewed_historical_red": frozenset(
        {"repository_audit", "downstream_consumer"}
    ),
    "reviewed_verification_gap": frozenset({"verification_gap"}),
    "reviewed_candidate_verification_passed": frozenset(
        {"repository_audit"}
    ),
    "independent_consumer_contract": frozenset({"downstream_consumer"}),
    "reviewed_candidate_regression": frozenset(
        {"repository_audit", "verification_gap"}
    ),
    "reviewed_candidate_safety_failure": frozenset(
        {"repository_audit", "verification_gap"}
    ),
    "reviewed_candidate_verification_inconclusive": frozenset(
        {"verification_gap"}
    ),
    "independent_consumer_rejection": frozenset({"downstream_consumer"}),
}
REVIEWED_VERIFICATION_PROOF_KINDS_BY_STATUS = {
    "passed": frozenset({"reviewed_candidate_verification_passed"}),
    "failed": frozenset(
        {
            "reviewed_candidate_regression",
            "reviewed_candidate_safety_failure",
        }
    ),
    "inconclusive": frozenset(
        {"reviewed_candidate_verification_inconclusive"}
    ),
}
ROLLBACK_PROOF_KIND_BY_BASIS = {
    "regression": "reviewed_candidate_regression",
    "safety": "reviewed_candidate_safety_failure",
    "consumer_rejection": "independent_consumer_rejection",
}
_CARRIER_ORDER = (
    "knowledge",
    "prompt_skill",
    "program_harness",
    "model_parameters",
)


class EvidenceRef(_StrictModel):
    evidence_id: Identifier
    subject_candidate_id: Identifier | None
    origin_kind: Literal[
        "repository_audit", "verification_gap", "downstream_consumer"
    ]
    repository: PublicText
    commit_sha: CommitSha
    tree_sha: CommitSha
    locator: PublicText
    proof_kind: ProofKind
    reviewed_summary: PublicText
    claim_scope: PublicText
    public_safe: Literal[True]


class Diagnosis(_StrictModel):
    status: Literal["confirmed", "inconclusive"]
    failure_mode_code: Identifier
    root_cause_layer: Literal[
        "knowledge",
        "prompt_skill",
        "program_harness",
        "evaluation_proof",
        "consumer_contract",
        "environment",
        "model_parameters",
    ]
    expected_invariant: PublicText
    observed_invariant: PublicText
    scope: PublicText


class CarrierAssessment(_StrictModel):
    carrier: Carrier
    disposition: Literal["selected", "rejected", "unsupported", "deferred"]
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)


class ChangeAction(_StrictModel):
    kind: Literal["change"]
    selected_carrier: Carrier
    change_surface: ChangeSurface
    runtime_effect: Literal["none", "changed"]


class NoChangeAction(_StrictModel):
    kind: Literal["no_change"]
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)


Action = Annotated[
    ChangeAction | NoChangeAction, Field(discriminator="kind")
]


class CapabilityIdentity(_StrictModel):
    profile_id: Identifier
    profile_version: Identifier
    proof_schema: Identifier


class CandidateRef(_StrictModel):
    candidate_id: Identifier
    carrier: Carrier
    change_surface: ChangeSurface
    repository: PublicText
    commit_sha: CommitSha
    tree_sha: CommitSha
    predecessor_or_rollback_ref: CommitSha
    capability_identity: CapabilityIdentity | None


class ReviewedDecision(_StrictModel):
    reviewed_candidate_verification_status: Literal[
        "passed", "failed", "inconclusive", "not_applicable"
    ]
    reviewed_verification_evidence_ids: list[Identifier] = Field(
        max_length=16
    )
    candidate_verdict: Literal[
        "accepted", "rejected", "need_more_evidence", "not_applicable"
    ]
    consumer_proof_status: Literal[
        "accepted", "rejected", "pending", "not_required"
    ]
    loop_closure_status: Literal[
        "closed_accepted",
        "closed_rejected",
        "closed_no_change",
        "open_waiting_evidence",
        "open_waiting_consumer",
    ]
    release_disposition: Literal[
        "hold", "eligible_for_separate_release_review", "rollback_recommended"
    ]
    rollback_basis: Literal[
        "regression", "safety", "consumer_rejection"
    ] | None
    rollback_evidence_ids: list[Identifier] = Field(max_length=16)
    rollback_subject_candidate_id: Identifier | None
    rollback_target: CommitSha | None
    reason_codes: list[Identifier] = Field(min_length=1, max_length=16)


class DecisionEpisode(_StrictModel):
    episode_id: Identifier
    predecessor_episode_id: Identifier | None
    input_evidence_ids: list[Identifier] = Field(min_length=1, max_length=256)
    diagnosis: Diagnosis
    carrier_assessments: list[CarrierAssessment] = Field(
        min_length=4, max_length=4
    )
    action: Action
    candidate_refs: list[CandidateRef] = Field(max_length=1)
    verification_profile_ref: VerificationProfileRef
    reviewed_decision: ReviewedDecision


class EvolutionCase(_StrictModel):
    schema_version: Literal["dra.evolution-case.v1"]
    case_id: Identifier
    case_version: Literal["1"]
    title: PublicText
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=256)
    episodes: list[DecisionEpisode] = Field(min_length=1, max_length=256)


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


def _valid_repository(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.path
        and parsed.path != "/"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and not any(ord(char) < 32 for char in value)
    )


def _unique(values: list[str]) -> bool:
    return len(values) == len(set(values))


def _raise(code: str) -> None:
    raise LoopContractError(code)


def _validate_case_semantics(case: EvolutionCase) -> None:
    evidence_by_id = {item.evidence_id: item for item in case.evidence_refs}
    if len(evidence_by_id) != len(case.evidence_refs):
        _raise("loop_evidence_ref_invalid")
    episode_by_id = {item.episode_id: item for item in case.episodes}
    if len(episode_by_id) != len(case.episodes):
        _raise("loop_episode_invalid")
    candidates = [
        candidate
        for episode in case.episodes
        for candidate in episode.candidate_refs
    ]
    candidate_by_id = {item.candidate_id: item for item in candidates}
    if len(candidate_by_id) != len(candidates):
        _raise("loop_candidate_identity_invalid")

    for evidence in case.evidence_refs:
        if not _valid_repository(evidence.repository):
            _raise("loop_evidence_ref_invalid")
        if (
            evidence.origin_kind
            not in ALLOWED_ORIGINS_BY_PROOF_KIND[evidence.proof_kind]
        ):
            _raise("loop_evidence_ref_invalid")
        requires_subject = evidence.proof_kind in SUBJECT_REQUIRED_PROOF_KINDS
        if requires_subject != (evidence.subject_candidate_id is not None):
            _raise("loop_evidence_ref_invalid")
        if (
            evidence.subject_candidate_id is not None
            and evidence.subject_candidate_id not in candidate_by_id
        ):
            _raise("loop_evidence_ref_invalid")
        if evidence.proof_kind == "reviewed_candidate_verification_passed":
            candidate = candidate_by_id[evidence.subject_candidate_id]
            if (
                evidence.repository,
                evidence.commit_sha,
                evidence.tree_sha,
            ) != (
                candidate.repository,
                candidate.commit_sha,
                candidate.tree_sha,
            ):
                _raise("loop_decision_invalid")

    consumed: set[str] = set()
    accepted_candidates: dict[str, CandidateRef] = {}
    for index, episode in enumerate(case.episodes):
        expected_predecessor = (
            None if index == 0 else case.episodes[index - 1].episode_id
        )
        if episode.predecessor_episode_id != expected_predecessor:
            _raise("loop_episode_invalid")
        if not _unique(episode.input_evidence_ids) or any(
            item not in evidence_by_id for item in episode.input_evidence_ids
        ):
            _raise("loop_episode_invalid")
        if [item.carrier for item in episode.carrier_assessments] != list(
            _CARRIER_ORDER
        ):
            _raise("loop_action_invalid")
        if any(
            not _unique(item.reason_codes)
            for item in episode.carrier_assessments
        ):
            _raise("loop_action_invalid")
        selected = [
            item.carrier
            for item in episode.carrier_assessments
            if item.disposition == "selected"
        ]
        model_assessment = episode.carrier_assessments[3]
        if model_assessment.disposition != "unsupported":
            _raise("loop_action_invalid")

        action = episode.action
        decision = episode.reviewed_decision
        if not _unique(decision.reviewed_verification_evidence_ids):
            _raise("loop_decision_invalid")
        if not _unique(decision.rollback_evidence_ids):
            _raise("loop_decision_invalid")
        if not _unique(decision.reason_codes):
            _raise("loop_decision_invalid")

        if isinstance(action, ChangeAction):
            if (
                len(selected) != 1
                or len(episode.candidate_refs) != 1
                or selected[0] != action.selected_carrier
                or action.selected_carrier == "model_parameters"
            ):
                _raise("loop_action_invalid")
            candidate = episode.candidate_refs[0]
            if not _valid_repository(candidate.repository):
                _raise("loop_candidate_identity_invalid")
            if (
                candidate.carrier != action.selected_carrier
                or candidate.change_surface != action.change_surface
            ):
                _raise("loop_action_invalid")
            if decision.reviewed_candidate_verification_status == "not_applicable":
                _raise("loop_decision_invalid")
            evidence_ids = decision.reviewed_verification_evidence_ids
            if not evidence_ids or any(
                item not in episode.input_evidence_ids for item in evidence_ids
            ):
                _raise("loop_decision_invalid")
            expected_kinds = REVIEWED_VERIFICATION_PROOF_KINDS_BY_STATUS[
                decision.reviewed_candidate_verification_status
            ]
            for evidence_id in evidence_ids:
                receipt = evidence_by_id[evidence_id]
                if (
                    receipt.proof_kind not in expected_kinds
                    or receipt.subject_candidate_id != candidate.candidate_id
                ):
                    _raise("loop_decision_invalid")
            if decision.candidate_verdict == "accepted":
                if (
                    episode.diagnosis.status != "confirmed"
                    or decision.reviewed_candidate_verification_status
                    != "passed"
                    or not any(
                        evidence_by_id[item].proof_kind
                        == "reviewed_historical_red"
                        for item in episode.input_evidence_ids
                    )
                ):
                    _raise("loop_decision_invalid")
                accepted_candidates[candidate.candidate_id] = candidate
            elif decision.reviewed_candidate_verification_status == "passed":
                _raise("loop_decision_invalid")
            if decision.reviewed_candidate_verification_status == "failed":
                if (
                    decision.candidate_verdict
                    not in {"rejected", "need_more_evidence"}
                    or decision.release_disposition != "hold"
                ):
                    _raise("loop_decision_invalid")
            if decision.reviewed_candidate_verification_status == "inconclusive":
                if (
                    decision.candidate_verdict != "need_more_evidence"
                    or decision.release_disposition != "hold"
                ):
                    _raise("loop_decision_invalid")
        else:
            if selected or episode.candidate_refs:
                _raise("loop_action_invalid")
            if (
                decision.reviewed_candidate_verification_status
                != "not_applicable"
                or decision.reviewed_verification_evidence_ids
                or decision.candidate_verdict != "not_applicable"
            ):
                _raise("loop_decision_invalid")

        if decision.consumer_proof_status == "pending":
            if (
                decision.loop_closure_status != "open_waiting_consumer"
                or decision.release_disposition != "hold"
            ):
                _raise("loop_decision_invalid")
        if decision.consumer_proof_status == "rejected":
            if decision.release_disposition == "eligible_for_separate_release_review":
                _raise("loop_decision_invalid")
        if decision.loop_closure_status == "closed_accepted":
            if (
                decision.candidate_verdict != "accepted"
                or decision.consumer_proof_status
                not in {"accepted", "not_required"}
            ):
                _raise("loop_decision_invalid")
        if decision.loop_closure_status == "closed_no_change":
            if (
                not isinstance(action, NoChangeAction)
                or decision.candidate_verdict != "not_applicable"
            ):
                _raise("loop_decision_invalid")
        if decision.release_disposition == "eligible_for_separate_release_review":
            if decision.loop_closure_status != "closed_accepted":
                _raise("loop_decision_invalid")

        rollback_fields_empty = (
            decision.rollback_basis is None
            and not decision.rollback_evidence_ids
            and decision.rollback_subject_candidate_id is None
            and decision.rollback_target is None
        )
        if decision.release_disposition != "rollback_recommended":
            if not rollback_fields_empty:
                _raise("loop_decision_invalid")
        else:
            if (
                index == 0
                or not isinstance(action, NoChangeAction)
                or decision.loop_closure_status != "closed_rejected"
                or decision.rollback_basis is None
                or not decision.rollback_evidence_ids
                or decision.rollback_subject_candidate_id
                not in accepted_candidates
            ):
                _raise("loop_decision_invalid")
            subject = accepted_candidates[
                decision.rollback_subject_candidate_id
            ]
            if decision.rollback_target != subject.predecessor_or_rollback_ref:
                _raise("loop_decision_invalid")
            expected_kind = ROLLBACK_PROOF_KIND_BY_BASIS[
                decision.rollback_basis
            ]
            for evidence_id in decision.rollback_evidence_ids:
                if (
                    evidence_id not in episode.input_evidence_ids
                    or evidence_id in consumed
                ):
                    _raise("loop_decision_invalid")
                evidence = evidence_by_id[evidence_id]
                if (
                    evidence.proof_kind != expected_kind
                    or evidence.subject_candidate_id
                    != decision.rollback_subject_candidate_id
                ):
                    _raise("loop_decision_invalid")
            if (
                decision.rollback_basis == "consumer_rejection"
                and decision.consumer_proof_status != "rejected"
            ):
                _raise("loop_decision_invalid")
        consumed.update(episode.input_evidence_ids)


CASE_ERROR_LOCATIONS = (
    ("reviewed_decision", "loop_decision_invalid"),
    ("candidate_refs", "loop_candidate_identity_invalid"),
    ("verification_profile_ref", "loop_verification_profile_invalid"),
    ("action", "loop_action_invalid"),
    ("carrier_assessments", "loop_action_invalid"),
    ("diagnosis", "loop_diagnosis_invalid"),
    ("episodes", "loop_episode_invalid"),
    ("evidence_refs", "loop_evidence_ref_invalid"),
)


def validate_case(value: Mapping[str, Any]) -> EvolutionCase:
    try:
        validate_public_projection(value)
    except LoopContractError:
        raise
    episodes = value.get("episodes")
    if isinstance(episodes, list):
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            action = episode.get("action")
            candidate_refs = episode.get("candidate_refs")
            if not isinstance(action, dict) or not isinstance(
                candidate_refs, list
            ):
                continue
            if (
                action.get("kind") == "change"
                and len(candidate_refs) != 1
            ) or (
                action.get("kind") == "no_change" and candidate_refs
            ):
                raise LoopContractError("loop_action_invalid")
    try:
        case = EvolutionCase.model_validate(value, strict=True)
    except ValidationError as exc:
        locations = {
            str(part)
            for error in exc.errors()
            for part in error.get("loc", ())
        }
        for segment, code in CASE_ERROR_LOCATIONS:
            if segment in locations:
                raise LoopContractError(code) from exc
        raise LoopContractError("loop_case_invalid") from exc
    _validate_case_semantics(case)
    validate_public_projection(case.model_dump(mode="json"))
    return case


def load_case_file(path: Path) -> EvolutionCase:
    try:
        raw = read_bounded_bytes(path, limit=MAX_CASE_BYTES)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("case")
        case = validate_case(value)
        if raw != canonical_json_bytes(case):
            raise ValueError("canonical")
        return case
    except LoopContractError:
        raise
    except (LoopBoundedReadError, ValueError, TypeError) as exc:
        raise LoopContractError("loop_case_invalid") from exc


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
