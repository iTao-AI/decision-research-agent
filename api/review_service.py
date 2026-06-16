"""Deterministic claim review rules for canonical research delivery."""
from __future__ import annotations

import uuid

from agent.talent_contracts import Claim, EvidenceSnapshot, Finding, ReviewBundle


def build_review_bundle(
    *,
    run_id: str,
    findings: list[Finding] | None = None,
    claims: list[Claim],
    evidence: list[EvidenceSnapshot],
    confidence_threshold: float,
    revision: int = 1,
) -> ReviewBundle:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    triggers: list[str] = []
    actions: list[str] = []

    for finding in findings or []:
        if not finding.evidence_refs:
            triggers.append(f"finding_without_evidence:{finding.finding_id}")
            actions.append(f"Attach evidence or remove finding {finding.finding_id}.")
        for ref in finding.evidence_refs:
            if ref not in evidence_by_id:
                triggers.append(f"missing_evidence_ref:{finding.finding_id}:{ref}")
                actions.append(
                    f"Attach evidence {ref} or revise finding {finding.finding_id}."
                )

    for claim in claims:
        if not claim.evidence_refs:
            triggers.append(f"claim_without_evidence:{claim.claim_id}")
            actions.append(f"Attach evidence or remove claim {claim.claim_id}.")
        for ref in claim.evidence_refs:
            if ref not in evidence_by_id:
                triggers.append(f"missing_evidence_ref:{claim.claim_id}:{ref}")
                actions.append(f"Attach evidence {ref} or revise claim {claim.claim_id}.")
        if claim.confidence < confidence_threshold:
            triggers.append(f"low_confidence:{claim.claim_id}")
            actions.append(f"Review confidence for claim {claim.claim_id}.")
        if claim.conflict_status == "conflicting":
            triggers.append(f"conflicting_sources:{claim.claim_id}")
            actions.append(f"Resolve conflicting sources for claim {claim.claim_id}.")
        if any(
            evidence_by_id.get(ref)
            and evidence_by_id[ref].verification_status == "unverified"
            for ref in claim.evidence_refs
        ):
            triggers.append(f"unverified_evidence:{claim.claim_id}")
            actions.append(f"Verify evidence for claim {claim.claim_id}.")

    status = "required" if triggers else "not_required"
    review_identity = "\n".join([run_id, str(revision), *triggers])
    return ReviewBundle(
        review_id=f"review_{uuid.uuid5(uuid.NAMESPACE_URL, review_identity).hex}",
        run_id=run_id,
        revision=revision,
        status=status,
        claim_snapshots=list(claims),
        evidence_snapshots=list(evidence),
        triggers=triggers,
        recommended_actions=actions,
        required_before_delivery=bool(triggers),
    )
