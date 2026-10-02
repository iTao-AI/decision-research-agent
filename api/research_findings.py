"""Application-owned, provider-free delivery from a frozen Evidence snapshot."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import html
import json
import re
from typing import Literal, get_args
from urllib.parse import quote

from pydantic import ValidationError

from agent.research import EvidenceEntry, evidence_fingerprint_for, source_identity_for
from agent.research_findings_contracts import (
    BoundFinding, BoundSourceReference, ResearchFindingsCandidate,
    ResearchFindingsDiagnostics, ResearchFindingsIssueCode, ResearchFindingsReport,
    ResearchFindingsScope,
)
from agent.source_url_policy import is_publishable_source_url


MAX_CANDIDATE_BYTES = 256 * 1024
# Each delivered artifact must fit the existing canonical result reader.
MAX_FINDINGS_ARTIFACT_BYTES = 1024 * 1024
RESEARCH_FINDINGS_PROFILE_ID = "generic-evidence-report"
RESEARCH_FINDINGS_PROFILE_VERSION = "1"


@dataclass(frozen=True)
class ResearchFindingsBuildResult:
    delivery_status: Literal["ready", "blocked"]
    report: ResearchFindingsReport | None
    artifacts: list[dict[str, str]]
    evidence_entries: list[EvidenceEntry]
    diagnostics: ResearchFindingsDiagnostics


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _artifact(artifact_id: str, kind: str, media_type: str, content: str) -> dict[str, str]:
    return {"artifact_id": artifact_id, "kind": kind, "media_type": media_type,
            "content": content, "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError("non-JSON numeric constant")


def _coverage_issues(candidate, scope: ResearchFindingsScope) -> list[ResearchFindingsIssueCode]:
    accepted = {q.question_id for q in scope.questions}
    found = {f.question_id for f in candidate.findings}
    dispositions = {d.question_id: d.status for d in candidate.dispositions}
    issues: list[ResearchFindingsIssueCode] = []
    if (found | dispositions.keys()) - accepted:
        issues.append("unknown_question_id")
    if accepted - dispositions.keys():
        issues.append("question_disposition_missing")
    if any((status == "candidate_findings") != (qid in found) for qid, status in dispositions.items()):
        issues.append("question_disposition_conflict")
    if not candidate.findings:
        issues.append("empty_research_output")
    return issues


def _occurrences(snippet: str, excerpt: str) -> list[int]:
    """Count contiguous occurrences, including overlapping ones, up to ambiguity."""
    offsets = []
    start = 0
    while len(offsets) < 2:
        offset = snippet.find(excerpt, start)
        if offset < 0:
            break
        offsets.append(offset)
        start = offset + 1
    return offsets


def _bind_reference(reference, entries: list[EvidenceEntry], run_id: str):
    if not is_publishable_source_url(reference.source_url):
        return None, "source_url_not_publishable"
    identity = source_identity_for(reference.source_url)
    observed = [entry for entry in entries if source_identity_for(entry.source_url) == identity]
    if not observed:
        return None, "source_not_observed"
    if any(not is_publishable_source_url(entry.source_url) for entry in observed):
        return None, "source_url_not_publishable"
    matches = [(entry, _occurrences(entry.snippet, reference.excerpt)) for entry in observed]
    matches = [(entry, offsets) for entry, offsets in matches if offsets]
    if not matches:
        return None, "excerpt_not_found"
    if len(matches) != 1 or len(matches[0][1]) != 1:
        return None, "ambiguous_reference"
    entry, offsets = matches[0]
    try:
        fingerprint = evidence_fingerprint_for(identity, entry.snippet)
    except UnicodeError:
        return None, "reference_binding_failed"
    if entry.source_identity != identity or entry.evidence_fingerprint != fingerprint:
        return None, "reference_binding_failed"
    try:
        bound = BoundSourceReference(
            evidence_id=f"ev_{run_id}_{entry.evidence_fingerprint}",
            evidence_fingerprint=entry.evidence_fingerprint,
            source_url=entry.source_url, source_identity=identity, snippet=entry.snippet,
            excerpt=reference.excerpt, excerpt_start=offsets[0],
            excerpt_end=offsets[0] + len(reference.excerpt),
        )
    except ValidationError:
        return None, "reference_binding_failed"
    return bound, None


def build_research_findings_artifacts(
    *, run_id: str, scope: ResearchFindingsScope, candidate_content: str | None,
    evidence_entries: list[EvidenceEntry], capture_issue: ResearchFindingsIssueCode | None = None,
) -> ResearchFindingsBuildResult:
    """Bind only the caller's current-run frozen ledger; never grant verification.

    EvidenceEntry has a conversation identity, not a run identity. The caller
    must pass only the current run's frozen entries. Persisted readers separately
    validate each row's run_id and ledger identity using the validator below.
    """
    scope = ResearchFindingsScope.model_validate(scope.model_dump(mode="json"))
    candidate = None
    issues: list[ResearchFindingsIssueCode] = []
    binding_failures = 0
    if capture_issue is not None:
        if capture_issue not in get_args(ResearchFindingsIssueCode):
            raise ValueError("invalid research findings capture issue")
        issues.append(capture_issue)
    elif candidate_content is None or candidate_content == "":
        issues.append("candidate_missing")
    else:
        try:
            if len(candidate_content.encode("utf-8")) > MAX_CANDIDATE_BYTES:
                issues.append("candidate_too_large")
            elif candidate_content.isspace():
                issues.append("candidate_missing")
            else:
                raw = json.loads(candidate_content, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                # Escaped lone surrogates are not publishable UTF-8 either.
                _canonical_json(raw).encode("utf-8")
        except (ValueError, UnicodeError, RecursionError):
            issues.append("candidate_invalid_json")
        if not issues:
            dispositions = raw.get("dispositions") if isinstance(raw, dict) else None
            if isinstance(dispositions, list):
                ids = [d.get("question_id") for d in dispositions if isinstance(d, dict)]
                if all(isinstance(qid, str) for qid in ids) and len(ids) != len(set(ids)):
                    issues.append("duplicate_question_disposition")
            if not issues:
                try:
                    candidate = ResearchFindingsCandidate.model_validate(raw)
                except ValidationError:
                    issues.append("candidate_contract_invalid")
    findings = []
    if candidate is not None:
        issues.extend(_coverage_issues(candidate, scope))
        for index, finding in enumerate(candidate.findings, 1):
            references = []
            for reference in finding.references:
                bound, issue = _bind_reference(reference, evidence_entries, run_id)
                if issue is not None:
                    issues.append(issue)
                    binding_failures += 1
                else:
                    references.append(bound)
            if len(references) == len(finding.references):
                findings.append(BoundFinding(finding_id=f"f{index}", question_id=finding.question_id,
                                             statement=finding.statement, references=references))
    report = None
    artifacts = []
    if not issues:
        report = ResearchFindingsReport(
            schema_version="dra.research-findings.v1", run_id=run_id,
            profile_id=RESEARCH_FINDINGS_PROFILE_ID, profile_version=RESEARCH_FINDINGS_PROFILE_VERSION,
            questions=scope.questions, findings=findings, dispositions=candidate.dispositions,
            reported_contradictions=candidate.reported_contradictions, limitations=candidate.limitations,
        )
        try:
            json_content = _canonical_json(report.model_dump(mode="json"))
            markdown = render_research_findings_markdown(report)
            if any(len(content.encode("utf-8")) > MAX_FINDINGS_ARTIFACT_BYTES for content in (json_content, markdown)):
                issues.append("artifact_package_too_large")
            else:
                artifacts = [
                    _artifact("research-findings.json", "research_findings_json", "application/json", json_content),
                    _artifact("research-report.md", "research_findings_markdown", "text/markdown", markdown),
                ]
        except UnicodeError:
            issues.append("reference_binding_failed")
    accepted = {q.question_id for q in scope.questions}
    diagnostics = ResearchFindingsDiagnostics(
        schema_version="dra.research-findings-diagnostics.v1", run_id=run_id,
        issue_codes=list(dict.fromkeys(issues)), requested_question_count=len(accepted),
        covered_question_count=len({f.question_id for f in candidate.findings} & accepted) if candidate else 0,
        unresolved_question_count=sum(d.question_id in accepted and d.status == "unresolved" for d in candidate.dispositions) if candidate else 0,
        reference_binding_failure_count=binding_failures,
    )
    if issues:
        return ResearchFindingsBuildResult("blocked", None, [
            _artifact("research-findings-diagnostics.json", "research_findings_diagnostics_json", "application/json",
                      _canonical_json(diagnostics.model_dump(mode="json")))
        ], list(evidence_entries), diagnostics)
    artifacts.append(_artifact(
        "research-findings-diagnostics.json", "research_findings_diagnostics_json", "application/json",
        _canonical_json(diagnostics.model_dump(mode="json")),
    ))
    cited = {reference.evidence_fingerprint for finding in findings for reference in finding.references}
    marked = [replace(entry, citation_status="cited" if entry.evidence_fingerprint in cited else "uncited") for entry in evidence_entries]
    return ResearchFindingsBuildResult("ready", report, artifacts, marked, diagnostics)


def _text(value: str) -> str:
    """Render untrusted strings as Markdown text, preserving visible content."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(value, quote=False))


def render_research_findings_markdown(report: ResearchFindingsReport) -> str:
    """Deterministic display of candidates and exact observed excerpts."""
    lines = ["# Research findings", "",
             "These are source-bound candidate findings. Sources remain unverified by this report; "
             "binding does not establish truth or entailment. Human verification and approval remain separate.", ""]
    for question in report.questions:
        lines.extend([f"## Question {_text(question.question_id)}: {_text(question.text)}", ""])
        disposition = next(d for d in report.dispositions if d.question_id == question.question_id)
        if disposition.status == "unresolved":
            lines.extend([f"Unresolved: {_text(disposition.reason)}", ""])
        else:
            for finding in report.findings:
                if finding.question_id != question.question_id:
                    continue
                lines.extend([f"### {_text(finding.finding_id)} — source-bound candidate", "", _text(finding.statement), ""])
                for reference in finding.references:
                    lines.extend([f"Source: <{quote(reference.source_url, safe=':/%')}>", "",
                                  f"Evidence: {_text(reference.evidence_id)}; "
                                  f"excerpt code-point offsets [{reference.excerpt_start}, {reference.excerpt_end}).", "",
                                  "Observed excerpt:", ""])
                    lines.extend("> " + _text(line) for line in reference.excerpt.split("\n"))
                    lines.extend(["", "Frozen observed snippet:", ""])
                    lines.extend("> " + _text(line) for line in reference.snippet.split("\n"))
                    lines.append("")
    lines.extend(["## Reported contradictions (model-reported)", ""])
    lines.extend([f"- {_text(item)}" for item in report.reported_contradictions] or ["None reported."])
    lines.extend(["", "## Limitations", ""])
    lines.extend([f"- {_text(item)}" for item in report.limitations] or ["None reported."])
    return "\n".join(lines) + "\n"


def validate_research_findings_report(
    report: ResearchFindingsReport, *, run_id: str, scope: ResearchFindingsScope,
    evidence_rows: list[dict],
) -> bool:
    """Independently re-check persisted same-run rows, not producer assertions.

    Artifact hashes prove bytes only. The reader must additionally invoke this
    validator and compare stored Markdown with render_research_findings_markdown.
    """
    try:
        # Reparse dumps: frozen Pydantic lists and model_copy are not authority.
        report = ResearchFindingsReport.model_validate(report.model_dump(mode="json"))
        scope = ResearchFindingsScope.model_validate(scope.model_dump(mode="json"))
        if (report.run_id != run_id or report.profile_id != RESEARCH_FINDINGS_PROFILE_ID
                or report.profile_version != RESEARCH_FINDINGS_PROFILE_VERSION
                or report.questions != scope.questions or _coverage_issues(report, scope)):
            return False
        if [f.finding_id for f in report.findings] != [f"f{i}" for i in range(1, len(report.findings) + 1)]:
            return False
        entries = []
        seen = set()
        for row in evidence_rows:
            url, snippet = row["source_url"], row["snippet"]
            if (row["run_id"] != run_id or (url is not None and type(url) is not str)
                    or type(snippet) is not str):
                return False
            identity = source_identity_for(url)
            fingerprint = evidence_fingerprint_for(identity, snippet)
            evidence_id = f"ev_{run_id}_{fingerprint}"
            if (row["source_identity"] != identity or row["evidence_fingerprint"] != fingerprint
                    or row["evidence_id"] != evidence_id or evidence_id in seen):
                return False
            seen.add(evidence_id)
            entries.append(EvidenceEntry(thread_id="", query_text="", subagent_name="", tool_name="",
                                         source_url=url, snippet=snippet))
        for finding in report.findings:
            for reference in finding.references:
                rebound, issue = _bind_reference(reference, entries, run_id)
                if issue is not None or rebound != reference:
                    return False
        contents = (_canonical_json(report.model_dump(mode="json")), render_research_findings_markdown(report))
        return all(len(content.encode("utf-8")) <= MAX_FINDINGS_ARTIFACT_BYTES for content in contents)
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return False
