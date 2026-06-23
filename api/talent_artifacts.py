"""Deterministic review and canonical artifact construction for Talent runs."""
from __future__ import annotations

from datetime import datetime
from collections import Counter
import hashlib
import json
from typing import Mapping

from agent.profile_registry import profile_registry
from agent.research import EvidenceEntry
from agent.talent_contracts import (
    DecisionBrief,
    EvidenceSnapshot,
    ResearchPacket,
    ResearchScope,
    ReviewBundle,
)
from api.decision_brief import render_markdown, with_content_hash
from api.review_service import build_review_bundle
from api.evidence_verification_models import EffectiveEvidenceVerification


def _canonical_hash(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_talent_artifacts(
    *,
    run_id: str,
    scope: dict,
    packets: list[ResearchPacket],
    evidence_entries: list[EvidenceEntry],
    generated_at: datetime,
    revision: int = 1,
    verification_snapshot_id: str | None = None,
    verification_snapshot_hash: str | None = None,
    verification_by_evidence_id: Mapping[
        str,
        EffectiveEvidenceVerification,
    ] | None = None,
    mandatory_review_triggers: tuple[str, ...] = (),
) -> tuple[ReviewBundle, DecisionBrief, list[dict]]:
    """Build review plus canonical JSON/Markdown artifacts without model calls."""
    profile = profile_registry.get("talent-hiring-signal")
    validated_scope = ResearchScope.model_validate(scope)
    findings = [finding for packet in packets for finding in packet.findings]
    claims = [claim for packet in packets for claim in packet.candidate_claims]
    evidence = []
    effective_items: list[EffectiveEvidenceVerification] = []
    for entry in evidence_entries:
        evidence_id = f"ev_{run_id}_{entry.evidence_fingerprint}"
        effective = (
            verification_by_evidence_id.get(evidence_id)
            if verification_by_evidence_id is not None
            else None
        )
        if effective is not None:
            if effective.evidence_fingerprint != entry.evidence_fingerprint:
                raise ValueError("verification_snapshot_evidence_mismatch")
            effective_items.append(effective)
        evidence.append(
            EvidenceSnapshot(
                evidence_id=evidence_id,
                source_url=entry.source_url,
                snippet=entry.snippet,
                verification_status=(
                    effective.verification_status
                    if effective is not None
                    else entry.verification_status
                ),
                verification_state=(
                    effective.verification_state
                    if effective is not None
                    else None
                ),
                verification_origin=(
                    effective.verification_origin
                    if effective is not None
                    else None
                ),
                verification_revision=(
                    effective.verification_revision
                    if effective is not None
                    else None
                ),
            )
        )
    review = build_review_bundle(
        run_id=run_id,
        findings=findings,
        claims=claims,
        evidence=evidence,
        confidence_threshold=0.6,
        revision=revision,
        mandatory_triggers=mandatory_review_triggers,
    )
    quality_summary = {
        "finding_count": len(findings),
        "claim_count": len(claims),
        "evidence_count": len(evidence),
    }
    if verification_snapshot_id is not None:
        quality_summary.update(
            {
                "publication_revision": revision,
                "verification_snapshot_id": verification_snapshot_id,
                "verification_snapshot_hash": verification_snapshot_hash,
                "verification_state_counts": dict(
                    sorted(
                        Counter(
                            item.verification_state
                            for item in effective_items
                        ).items()
                    )
                ),
                "verification_origin_counts": dict(
                    sorted(
                        Counter(
                            item.verification_origin
                            for item in effective_items
                        ).items()
                    )
                ),
            }
        )
    brief = with_content_hash(
        DecisionBrief(
            schema_version=profile.brief_schema_version,
            run_id=run_id,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            input_snapshot_hash=_canonical_hash(validated_scope.model_dump(mode="json")),
            renderer_version=profile.renderer_version,
            canonicalization_version=profile.canonicalization_version,
            scope=validated_scope,
            executive_summary=(
                f"Declared-scope research produced {len(findings)} findings "
                f"and {len(claims)} candidate claims."
            ),
            findings=findings,
            claims=claims,
            evidence_summary=[item.model_dump(mode="json") for item in evidence],
            conflicts=[item for packet in packets for item in packet.contradictions],
            limitations=[item for packet in packets for item in packet.limitations],
            recommendations=[],
            review_summary=review.model_dump(mode="json"),
            quality_summary=quality_summary,
            generated_at=generated_at,
        )
    )
    if revision < 1:
        raise ValueError("revision must be at least 1")
    if revision == 1:
        json_artifact_id = "decision-brief.json"
        markdown_artifact_id = "decision-brief.md"
    else:
        json_artifact_id = f"decision-brief.r{revision}.json"
        markdown_artifact_id = f"decision-brief.r{revision}.md"
    artifacts = [
        {
            "artifact_id": json_artifact_id,
            "kind": "decision_brief_json",
            "media_type": "application/json",
            "content": json.dumps(
                brief.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "content_hash": brief.content_hash,
        },
        {
            "artifact_id": markdown_artifact_id,
            "kind": "decision_brief_markdown",
            "media_type": "text/markdown",
            "content": render_markdown(brief),
            "content_hash": brief.content_hash,
        },
    ]
    return review, brief, artifacts
