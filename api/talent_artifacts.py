"""Deterministic review and canonical artifact construction for Talent runs."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

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
) -> tuple[ReviewBundle, DecisionBrief, list[dict]]:
    """Build review plus canonical JSON/Markdown artifacts without model calls."""
    profile = profile_registry.get("talent-hiring-signal")
    validated_scope = ResearchScope.model_validate(scope)
    findings = [finding for packet in packets for finding in packet.findings]
    claims = [claim for packet in packets for claim in packet.candidate_claims]
    evidence = [
        EvidenceSnapshot(
            evidence_id=f"ev_{run_id}_{entry.evidence_fingerprint}",
            source_url=entry.source_url,
            snippet=entry.snippet,
            verification_status=entry.verification_status,
        )
        for entry in evidence_entries
    ]
    review = build_review_bundle(
        run_id=run_id,
        findings=findings,
        claims=claims,
        evidence=evidence,
        confidence_threshold=0.6,
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
            quality_summary={
                "finding_count": len(findings),
                "claim_count": len(claims),
                "evidence_count": len(evidence),
            },
            generated_at=generated_at,
        )
    )
    artifacts = [
        {
            "artifact_id": "decision-brief.json",
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
            "artifact_id": "decision-brief.md",
            "kind": "decision_brief_markdown",
            "media_type": "text/markdown",
            "content": render_markdown(brief),
            "content_hash": brief.content_hash,
        },
    ]
    return review, brief, artifacts
