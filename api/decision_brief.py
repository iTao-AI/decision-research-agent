"""Canonical DecisionBrief hashing and deterministic Markdown rendering."""
from __future__ import annotations

from datetime import datetime
import hashlib
import html
import json
import math
import re
import unicodedata
from typing import Any, Iterable

from agent.talent_contracts import Claim, DecisionBrief, Finding


_KNOWN_EVIDENCE_STATUSES = frozenset({"verified", "unverified"})
_KNOWN_REVIEW_STATUSES = frozenset({"not_required", "required", "resolved"})
_MARKDOWN_STRUCTURE = re.compile(r"([\\`*_\[\]()#!|])")
_NOT_DECLARED = "Not declared"
_SNAPSHOT_LIMIT = 3


def _canonical_payload(brief: DecisionBrief) -> bytes:
    payload = brief.model_dump(
        mode="json",
        exclude={"generated_at", "content_hash"},
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def with_content_hash(brief: DecisionBrief) -> DecisionBrief:
    content_hash = hashlib.sha256(_canonical_payload(brief)).hexdigest()
    return brief.model_copy(update={"content_hash": content_hash})


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _string_items(value: Any) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str) and item]


def _plain_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return _NOT_DECLARED
    normalized = (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .replace("\t", " ")
    )
    printable = "".join(
        character
        for character in normalized
        if character == "\n" or not unicodedata.category(character).startswith("C")
    )
    escaped = _MARKDOWN_STRUCTURE.sub(r"\\\1", printable)
    escaped = html.escape(escaped, quote=True)
    return escaped.replace("\n", "<br>") or _NOT_DECLARED


def _joined(value: Any) -> str:
    items = [_plain_text(item) for item in _string_items(value)]
    return "; ".join(items) if items else "None declared"


def _confidence(value: Any) -> str:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    ):
        return f"{value:.0%}"
    return _NOT_DECLARED


def _datetime(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else _NOT_DECLARED


def _evidence_index(evidence_summary: Any) -> dict[str, str]:
    """Index only unambiguous IDs with a known verification status."""
    statuses: dict[str, str] = {}
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in _as_list(evidence_summary):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            continue
        if evidence_id in seen:
            duplicates.add(evidence_id)
            statuses.pop(evidence_id, None)
            continue
        seen.add(evidence_id)
        status = item.get("verification_status")
        if isinstance(status, str) and status in _KNOWN_EVIDENCE_STATUSES:
            statuses[evidence_id] = status
    for evidence_id in duplicates:
        statuses.pop(evidence_id, None)
    return statuses


def _has_global_conflicts(conflicts: Any) -> bool:
    if conflicts in (None, []):
        return False
    if not isinstance(conflicts, (list, tuple)):
        return True
    return bool(conflicts)


def _finding_refs(finding: Finding) -> list[str]:
    return _string_items(getattr(finding, "evidence_refs", None))


def _is_snapshot_eligible(
    finding: Finding,
    evidence_by_id: dict[str, str],
    *,
    global_conflicts: bool,
) -> bool:
    refs = _finding_refs(finding)
    if not refs or global_conflicts:
        return False
    if _has_global_conflicts(getattr(finding, "contradictions", None)):
        return False
    return all(evidence_by_id.get(ref) == "verified" for ref in refs)


def _snapshot_exclusion_reasons(
    finding: Finding,
    evidence_by_id: dict[str, str],
    *,
    global_conflicts: bool,
) -> list[str]:
    refs = _finding_refs(finding)
    reasons: list[str] = []
    if not refs:
        reasons.append("No evidence refs declared.")
    unresolved = [ref for ref in refs if ref not in evidence_by_id]
    if unresolved:
        reasons.append(f"Unresolved evidence refs: {_joined(unresolved)}")
    unverified = [
        ref for ref in refs if evidence_by_id.get(ref) == "unverified"
    ]
    if unverified:
        reasons.append(f"Unverified evidence refs: {_joined(unverified)}")
    if _has_global_conflicts(getattr(finding, "contradictions", None)):
        reasons.append("Finding contradictions declared.")
    if global_conflicts:
        reasons.append("Brief-level conflicts declared.")
    return reasons or ["Snapshot eligibility could not be established."]


def _review_status(review_summary: Any) -> str:
    if not isinstance(review_summary, dict):
        return _NOT_DECLARED
    status = review_summary.get("status")
    return (
        status
        if isinstance(status, str) and status in _KNOWN_REVIEW_STATUSES
        else _NOT_DECLARED
    )


def _review_required(review_summary: Any) -> str:
    if not isinstance(review_summary, dict):
        return _NOT_DECLARED
    value = review_summary.get("required_before_delivery")
    if type(value) is bool:
        return "Yes" if value else "No"
    return _NOT_DECLARED


def _declared_scope(brief: DecisionBrief) -> str:
    scope = brief.scope
    roles = ", ".join(_plain_text(item) for item in scope.target_roles)
    companies = ", ".join(_plain_text(item) for item in scope.target_companies)
    return (
        f"Roles: {roles or 'None declared'}; "
        f"Companies: {companies or 'None declared'}; "
        f"Window: {scope.time_window.start.isoformat()} to "
        f"{scope.time_window.end.isoformat()}; "
        f"Declared source references: {len(scope.declared_samples)}"
    )


def _render_finding_summary(finding: Finding) -> str:
    return "\n".join(
        (
            f"#### {_plain_text(finding.finding_id)}",
            "",
            f"- Finding: {_plain_text(finding.statement)}",
            f"- Sample scope: {_plain_text(finding.sample_scope)}",
            f"- Evidence refs: {_joined(finding.evidence_refs)}",
            f"- Declared confidence: {_confidence(finding.confidence)}",
        )
    )


def _render_decision_snapshot(
    brief: DecisionBrief,
    evidence_by_id: dict[str, str],
) -> str:
    findings = [item for item in _as_list(brief.findings) if isinstance(item, Finding)]
    claims = [item for item in _as_list(brief.claims) if isinstance(item, Claim)]
    evidence_records = _as_list(brief.evidence_summary)
    global_conflicts = _has_global_conflicts(brief.conflicts)
    eligible = [
        finding
        for finding in findings
        if _is_snapshot_eligible(
            finding,
            evidence_by_id,
            global_conflicts=global_conflicts,
        )
    ]
    if not findings:
        eligibility = "No findings are present in this brief."
    elif eligible:
        eligibility = (
            f"{len(eligible)} verified evidence-backed findings; "
            f"{min(len(eligible), _SNAPSHOT_LIMIT)} shown (presentation-only)."
        )
    else:
        eligibility = (
            "No verified evidence-backed findings are available for the snapshot."
        )
    table = "\n".join(
        (
            "| Item | Value |",
            "|---|---|",
            f"| Declared scope | {_declared_scope(brief)} |",
            f"| Findings | {len(findings)} |",
            f"| Candidate claims | {len(claims)} |",
            f"| Evidence records | {len(evidence_records)} |",
            f"| Review bundle status | {_review_status(brief.review_summary)} |",
            "| Review required before delivery | "
            f"{_review_required(brief.review_summary)} |",
            f"| Snapshot eligibility | {eligibility} |",
        )
    )
    if eligible:
        details = "\n\n".join(
            _render_finding_summary(finding)
            for finding in eligible[:_SNAPSHOT_LIMIT]
        )
    else:
        details = eligibility
    return f"## Decision Snapshot\n\n{table}\n\n### Evidence-backed findings\n\n{details}"


def _render_scope(brief: DecisionBrief) -> str:
    scope = brief.scope
    declared_types = [sample.source_type for sample in scope.declared_samples]
    return "\n".join(
        (
            "## Scope And Coverage",
            "",
            f"- Target roles: {_joined(scope.target_roles)}",
            f"- Target companies: {_joined(scope.target_companies)}",
            "- Time window: "
            f"{scope.time_window.start.isoformat()} to {scope.time_window.end.isoformat()}",
            f"- Declared source references: {len(scope.declared_samples)}",
            f"- Declared source types: {_joined(declared_types)}",
            f"- Allowed source types: {_joined(scope.allowed_source_types)}",
            f"- Research questions: {_joined(scope.research_questions)}",
            f"- Requested outputs: {_joined(scope.requested_outputs)}",
        )
    )


def _render_needs_verification(
    brief: DecisionBrief,
    evidence_by_id: dict[str, str],
) -> str | None:
    findings = [item for item in _as_list(brief.findings) if isinstance(item, Finding)]
    claims = [item for item in _as_list(brief.claims) if isinstance(item, Claim)]
    global_conflicts = _has_global_conflicts(brief.conflicts)
    ineligible = [
        finding
        for finding in findings
        if not _is_snapshot_eligible(
            finding,
            evidence_by_id,
            global_conflicts=global_conflicts,
        )
    ]
    if not ineligible and not claims:
        return None
    sections = ["## Needs Verification"]
    if ineligible:
        blocks = []
        for finding in ineligible:
            reasons = "; ".join(
                reason.rstrip(".")
                for reason in _snapshot_exclusion_reasons(
                    finding,
                    evidence_by_id,
                    global_conflicts=global_conflicts,
                )
            ) + "."
            blocks.append(
                "\n".join(
                    (
                        f"#### {_plain_text(finding.finding_id)}",
                        "",
                        f"- Finding: {_plain_text(finding.statement)}",
                        f"- Evidence refs: {_joined(finding.evidence_refs)}",
                        f"- Snapshot exclusion: {reasons}",
                    )
                )
            )
        sections.append("### Findings\n\n" + "\n\n".join(blocks))
    if claims:
        blocks = []
        for claim in claims:
            blocks.append(
                "\n".join(
                    (
                        f"#### {_plain_text(claim.claim_id)}",
                        "",
                        f"- Candidate claim: {_plain_text(claim.text)}",
                        "- Verification status: "
                        f"{_plain_text(claim.verification_status)}",
                        f"- Review status: {_plain_text(claim.review_status)}",
                        f"- Conflict status: {_plain_text(claim.conflict_status)}",
                        f"- Evidence refs: {_joined(claim.evidence_refs)}",
                        "- Snapshot placement: Candidate claims are never "
                        "snapshot-eligible in renderer v2.",
                    )
                )
            )
        sections.append("### Candidate Claims\n\n" + "\n\n".join(blocks))
    return "\n\n".join(sections)


def _render_boundaries(brief: DecisionBrief) -> str | None:
    findings = [item for item in _as_list(brief.findings) if isinstance(item, Finding)]
    claims = [item for item in _as_list(brief.claims) if isinstance(item, Claim)]
    groups: list[tuple[str, list[str]]] = []

    gaps = [
        f"{_plain_text(finding.finding_id)}: {_plain_text(gap)}"
        for finding in findings
        for gap in _string_items(finding.evidence_gaps)
    ]
    contradictions = [
        f"{_plain_text(finding.finding_id)}: {_plain_text(conflict)}"
        for finding in findings
        for conflict in _string_items(finding.contradictions)
    ]
    claim_conflicts = [
        f"{_plain_text(claim.claim_id)}: conflicting"
        for claim in claims
        if claim.conflict_status == "conflicting"
    ]
    brief_conflicts = [_plain_text(item) for item in _string_items(brief.conflicts)]
    review = brief.review_summary if isinstance(brief.review_summary, dict) else {}
    triggers = [_plain_text(item) for item in _string_items(review.get("triggers"))]

    for heading, items in (
        ("Evidence Gaps", gaps),
        ("Finding Contradictions", contradictions),
        ("Claim Conflicts", claim_conflicts),
        ("Brief Conflicts", brief_conflicts),
        ("Review Triggers", triggers),
    ):
        if items:
            groups.append((heading, items))
    if not groups:
        return None
    rendered = ["## Evidence Gaps And Conflicts"]
    for heading, items in groups:
        rendered.append(f"### {heading}\n\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(rendered)


def _render_finding_appendix(finding: Finding) -> str:
    return "\n".join(
        (
            f"### {_plain_text(finding.finding_id)}",
            "",
            f"- Research question: {_plain_text(finding.research_question_id)}",
            f"- Statement: {_plain_text(finding.statement)}",
            f"- Sample scope: {_plain_text(finding.sample_scope)}",
            f"- Declared confidence: {_confidence(finding.confidence)}",
            f"- Evidence refs: {_joined(finding.evidence_refs)}",
            f"- Observed at: {_datetime(finding.observed_at)}",
            f"- Evidence gaps: {_joined(finding.evidence_gaps)}",
            f"- Contradictions: {_joined(finding.contradictions)}",
            f"- Limitations: {_joined(finding.limitations)}",
        )
    )


def _render_findings_appendix(brief: DecisionBrief) -> str:
    findings = [item for item in _as_list(brief.findings) if isinstance(item, Finding)]
    if not findings:
        details = "No findings are present in this brief."
    else:
        details = "\n\n".join(_render_finding_appendix(item) for item in findings)
    return f"## Detailed Findings Appendix\n\n{details}"


def _render_claim_appendix(claim: Claim) -> str:
    return "\n".join(
        (
            f"### {_plain_text(claim.claim_id)}",
            "",
            f"- Candidate claim: {_plain_text(claim.text)}",
            f"- Type: {_plain_text(claim.claim_type)}",
            f"- Finding refs: {_joined(claim.finding_refs)}",
            f"- Evidence refs: {_joined(claim.evidence_refs)}",
            f"- Declared confidence: {_confidence(claim.confidence)}",
            f"- Citation status: {_plain_text(claim.citation_status)}",
            f"- Verification status: {_plain_text(claim.verification_status)}",
            f"- Review status: {_plain_text(claim.review_status)}",
            f"- Conflict status: {_plain_text(claim.conflict_status)}",
            f"- Limitations: {_joined(claim.limitations)}",
        )
    )


def _render_claims_appendix(brief: DecisionBrief) -> str:
    claims = [item for item in _as_list(brief.claims) if isinstance(item, Claim)]
    if not claims:
        details = "No candidate claims are present in this brief."
    else:
        details = "\n\n".join(_render_claim_appendix(item) for item in claims)
    return f"## Candidate Claims Appendix\n\n{details}"


def _render_metadata(brief: DecisionBrief) -> str:
    return "\n".join(
        (
            "## Artifact Metadata",
            "",
            f"- Run ID: {_plain_text(brief.run_id)}",
            "- Profile: "
            f"{_plain_text(brief.profile_id)}@{_plain_text(brief.profile_version)}",
            f"- Brief schema version: {_plain_text(brief.schema_version)}",
            f"- Renderer version: {_plain_text(brief.renderer_version)}",
            "- Canonicalization version: "
            f"{_plain_text(brief.canonicalization_version)}",
            f"- Input snapshot hash: {_plain_text(brief.input_snapshot_hash)}",
            f"- Content hash: {_plain_text(brief.content_hash)}",
            f"- Generated at: {_datetime(brief.generated_at)}",
        )
    )


def _render_bullets(heading: str, items: Iterable[str]) -> str | None:
    rendered = [_plain_text(item) for item in items if isinstance(item, str) and item]
    if not rendered:
        return None
    return f"## {heading}\n\n" + "\n".join(f"- {item}" for item in rendered)


def render_markdown(brief: DecisionBrief) -> str:
    """Render stable Markdown from canonical JSON; no model calls or file tools."""
    evidence_by_id = _evidence_index(brief.evidence_summary)
    sections: list[str | None] = [
        "# Talent Hiring Signal Decision Brief",
        _render_decision_snapshot(brief, evidence_by_id),
        _render_scope(brief),
        _render_needs_verification(brief, evidence_by_id),
        _render_boundaries(brief),
        _render_bullets("Limitations", _string_items(brief.limitations)),
        _render_findings_appendix(brief),
        _render_claims_appendix(brief),
        _render_metadata(brief),
        _render_bullets("Recommendations", _string_items(brief.recommendations)),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"
