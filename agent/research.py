"""Research run and evidence ledger contracts.

These helpers keep research evidence auditable without depending on the
LLM-backed agent runtime. Runtime integration happens through AgentRunResult
and the task finalizer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
_MAX_SNIPPET_LENGTH = 1000
_MAX_EVIDENCE_PER_TOOL_MESSAGE = 10
_URL_TRAILING_PUNCTUATION = ".,;:!?"


@dataclass(frozen=True)
class EvidenceEntry:
    """One source-like item observed from a tool message."""

    thread_id: str
    query_text: str
    subagent_name: str
    tool_name: str
    source_url: str | None
    snippet: str
    source_identity: str = ""
    evidence_fingerprint: str = ""
    retrieved_at: str | None = None
    tool_call_id: str | None = None
    citation_status: str = "uncited"
    verification_status: str = "unverified"
    baseline_verification_origin: str = "none"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __post_init__(self) -> None:
        if self.baseline_verification_origin not in {"none", "declared_fixture"}:
            raise ValueError("invalid baseline_verification_origin")
        source_identity = self.source_identity or source_identity_for(self.source_url)
        fingerprint = self.evidence_fingerprint or evidence_fingerprint_for(
            source_identity, self.snippet
        )
        object.__setattr__(self, "source_identity", source_identity)
        object.__setattr__(self, "evidence_fingerprint", fingerprint)


@dataclass(frozen=True)
class QualityReport:
    """Structured quality gate result for a generated research report."""

    status: str
    issues: list[dict[str, str]]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truncate(value: Any, max_length: int = _MAX_SNIPPET_LENGTH) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 24] + f"... (truncated, {len(text)} chars)"


def _loads_json_like(content: Any) -> Any:
    if not isinstance(content, str):
        return content
    stripped = content.strip()
    if not stripped or stripped[0] not in "[{":
        return content
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return content


def _url_from_mapping(item: dict[str, Any]) -> str | None:
    for key in ("url", "source_url", "link", "href"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _normalize_url(url: str) -> str:
    return url.rstrip(_URL_TRAILING_PUNCTUATION)


def source_identity_for(source_url: str | None) -> str:
    return _normalize_url(source_url.strip()) if source_url else "source:unknown"


def normalize_evidence_content(content: str) -> str:
    return " ".join(str(content).split())


def evidence_fingerprint_for(source_identity: str, content: str) -> str:
    payload = f"{source_identity}\n{normalize_evidence_content(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evidence_id_for(source_url: str | None, content: str, *, run_id: str) -> str:
    """Return the stable ledger identity exposed to structured researchers."""
    fingerprint = evidence_fingerprint_for(
        source_identity_for(source_url),
        _truncate(content),
    )
    return f"ev_{run_id}_{fingerprint}"


def merge_evidence_entries(*entry_groups: list[EvidenceEntry]) -> list[EvidenceEntry]:
    """Merge evidence using normalized source plus normalized content identity."""
    merged: list[EvidenceEntry] = []
    seen: set[str] = set()
    for entries in entry_groups:
        for entry in entries:
            if entry.evidence_fingerprint in seen:
                continue
            seen.add(entry.evidence_fingerprint)
            merged.append(entry)
    return merged


def _snippet_from_mapping(item: dict[str, Any]) -> str:
    for key in ("content", "snippet", "raw_content", "answer", "summary", "title"):
        value = item.get(key)
        if value:
            return _truncate(value)
    return _truncate(item)


def extract_evidence_entries(
    *,
    thread_id: str,
    query_text: str,
    subagent_name: str,
    tool_name: str,
    content: Any,
) -> list[EvidenceEntry]:
    """Extract source-like evidence entries from tool output.

    Supports common Tavily-style mappings, JSON strings, lists of mappings,
    and plain text containing URLs. Entries are best-effort and start as
    unverified/uncited until final report text is compared during finalization.
    """
    parsed = _loads_json_like(content)
    entries: list[EvidenceEntry] = []

    if isinstance(parsed, dict):
        if isinstance(parsed.get("results"), list):
            items = parsed["results"]
        else:
            items = [parsed]
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        source_url = _url_from_mapping(item)
        if source_url is None:
            continue
        entries.append(
            EvidenceEntry(
                thread_id=thread_id,
                query_text=query_text,
                subagent_name=subagent_name,
                tool_name=tool_name,
                source_url=_normalize_url(source_url),
                snippet=_snippet_from_mapping(item),
            )
        )
        if len(entries) >= _MAX_EVIDENCE_PER_TOOL_MESSAGE:
            return entries

    if entries:
        return entries

    text = _truncate(parsed)
    urls = _URL_RE.findall(text)
    if urls:
        for url in urls[:_MAX_EVIDENCE_PER_TOOL_MESSAGE]:
            entries.append(
                EvidenceEntry(
                    thread_id=thread_id,
                    query_text=query_text,
                    subagent_name=subagent_name,
                    tool_name=tool_name,
                    source_url=_normalize_url(url),
                    snippet=text,
                )
            )
        return entries

    return []


def _url_is_cited(source_url: str, report_text: str) -> bool:
    for match in _URL_RE.finditer(report_text):
        if _normalize_url(match.group(0)) == source_url:
            return True
    return False


def mark_cited_evidence(
    entries: list[EvidenceEntry], report_text: str
) -> list[EvidenceEntry]:
    """Mark evidence as cited when its source URL appears in the final report."""
    marked: list[EvidenceEntry] = []
    for entry in entries:
        if entry.source_url and _url_is_cited(entry.source_url, report_text):
            marked.append(replace(entry, citation_status="cited"))
        else:
            marked.append(entry)
    return marked


def _read_report_text(report_path: Path | None) -> str:
    if report_path is None or not report_path.exists() or not report_path.is_file():
        return ""
    try:
        return report_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def evaluate_report_quality(
    *,
    report_path: Path | None,
    fallback_used: bool,
    evidence_entries: list[EvidenceEntry],
    token_usage: dict[str, Any],
    diagnostics: list[str],
    token_warning_threshold: int = 1_000_000,
) -> QualityReport:
    """Evaluate report quality with deterministic, auditable gates."""
    report_size = 0
    if report_path is not None and report_path.exists() and report_path.is_file():
        report_size = report_path.stat().st_size

    cited_count = sum(
        1 for entry in evidence_entries if entry.citation_status == "cited"
    )
    total_tokens = int(token_usage.get("total_tokens") or 0)
    issues: list[dict[str, str]] = []

    if report_path is None or report_size == 0:
        issues.append(
            {
                "code": "empty_report",
                "severity": "error",
                "message": "No non-empty report was produced.",
            }
        )
    if fallback_used:
        issues.append(
            {
                "code": "fallback_report",
                "severity": "error",
                "message": "The task completed with a system fallback report.",
            }
        )
    if not evidence_entries:
        issues.append(
            {
                "code": "no_evidence_entries",
                "severity": "warning",
                "message": "No source-like evidence entries were captured.",
            }
        )
    elif cited_count == 0:
        issues.append(
            {
                "code": "no_cited_evidence",
                "severity": "warning",
                "message": "Evidence was captured but no source URL appears in the report.",
            }
        )
    if total_tokens > token_warning_threshold:
        issues.append(
            {
                "code": "token_budget_exceeded",
                "severity": "warning",
                "message": "Token usage exceeded the configured warning threshold.",
            }
        )

    status = "passed"
    if any(issue["severity"] == "error" for issue in issues):
        status = "failed"
    elif issues:
        status = "warning"

    return QualityReport(
        status=status,
        issues=issues,
        metrics={
            "report_size_bytes": report_size,
            "evidence_count": len(evidence_entries),
            "cited_evidence_count": cited_count,
            "total_tokens": total_tokens,
            "diagnostic_count": len(diagnostics),
        },
    )


def prepare_final_evidence(
    entries: list[EvidenceEntry], report_path: Path | None
) -> list[EvidenceEntry]:
    """Apply final report citation matching before persistence."""
    return mark_cited_evidence(entries, _read_report_text(report_path))
