# Talent DecisionBrief Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canonical Talent DecisionBrief immediately scannable through a deterministic executive snapshot, evidence-bound capability matrix, candidate-claim table, and explicit boundaries without expanding the research schema or generating new hiring advice.

**Architecture:** Keep `ResearchPacket`, `DecisionBrief`, review, API, and persistence contracts unchanged. Build a concise summary from existing findings/claims/evidence in `api/talent_artifacts.py`, then render the canonical fields through pure Markdown helpers in `api/decision_brief.py`; increment only the Talent renderer version and verify the result with focused tests plus the fixed 1x2 and 3x2 benchmark gates.

**Tech Stack:** Python 3.11, Pydantic v2, deterministic JSON/Markdown artifacts, pytest, existing Talent value-gate runner.

**Source Spec:** `docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md`

---

## Delivery Boundaries

**In scope:** deterministic summary construction, Markdown escaping, executive snapshot, capability matrix, candidate-claim table, evidence gaps, review triggers, conflicts, limitations, conditional recommendations, renderer version `2`, tests, and benchmark procedure documentation.

**Not in scope:** new Pydantic fields, prompt changes, model calls, JD recommendations, interview questions, API/database/frontend changes, LLM review, LangSmith business state, Skills, Async Subagents, or P1B durable HITL.

## File Structure

| Responsibility | Files |
|---|---|
| Summary construction | Modify `api/talent_artifacts.py`; test in `tests/unit/test_talent_artifacts.py` |
| Markdown presentation | Modify `api/decision_brief.py`; test in `tests/unit/test_decision_brief.py` |
| Renderer contract version | Modify `agent/profile_registry.py`; test in `tests/unit/test_profile_registry.py` |
| Verification runbook | Modify `benchmarks/talent-hiring-signal-v1/README.md` |
| Approved design correction | Modify `docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md` to include claim limitations and review triggers |

No new runtime module is needed. The existing two modules already own artifact construction and presentation.

### Task 1: Version And Evidence-Bound Executive Summary

**Files:**
- Modify: `tests/unit/test_profile_registry.py`
- Modify: `tests/unit/test_talent_artifacts.py`
- Modify: `agent/profile_registry.py:61-72`
- Modify: `api/talent_artifacts.py:21-85`

- [ ] **Step 1: Write the failing renderer-version contract test**

Add to `tests/unit/test_profile_registry.py`:

```python
def test_talent_profile_uses_renderer_v2_without_schema_version_change():
    from agent.profile_registry import profile_registry

    profile = profile_registry.get("talent-hiring-signal")

    assert profile.renderer_version == "2"
    assert profile.brief_schema_version == "1"
    assert profile.canonicalization_version == "1"
```

- [ ] **Step 2: Write failing summary tests**

In `tests/unit/test_talent_artifacts.py`, extend
`test_talent_artifacts_are_deterministic_and_require_review_for_unknown_evidence`
after the current determinism assertions:

```python
    brief = first[1]
    assert brief.renderer_version == "2"
    assert brief.schema_version == "1"
    assert brief.canonicalization_version == "1"
    assert brief.executive_summary == (
        "Declared-scope research produced 1 finding, 1 candidate claim, "
        "and 0 evidence records. Highest-confidence decision signals: Claim. "
        "Conclusions are limited to the declared scope."
    )
```

Add a fallback test that proves the summary does not invent a claim:

```python
def test_talent_summary_falls_back_to_ranked_findings_without_claims():
    from agent.talent_contracts import ResearchPacket
    from api.talent_artifacts import build_talent_artifacts

    packet = ResearchPacket.model_validate(
        {
            "packet_id": "packet-1",
            "scope_id": "scope-1",
            "findings": [
                {
                    "finding_id": "finding-low",
                    "research_question_id": "question-1",
                    "statement": "Lower-confidence signal.",
                    "evidence_refs": ["ev-low"],
                    "sample_scope": "declared",
                    "confidence": 0.6,
                },
                {
                    "finding_id": "finding-high",
                    "research_question_id": "question-1",
                    "statement": "Higher-confidence signal.",
                    "evidence_refs": ["ev-high"],
                    "sample_scope": "declared",
                    "confidence": 0.9,
                },
            ],
            "candidate_claims": [],
        }
    )
    scope = {
        "target_roles": ["AI Agent Engineer"],
        "target_companies": [],
        "time_window": {"start": "2026-01-01", "end": "2026-06-12"},
        "declared_samples": [],
        "allowed_source_types": ["public_job_posting"],
        "research_questions": ["question-1"],
        "requested_outputs": ["decision_brief"],
    }

    _, brief, _ = build_talent_artifacts(
        run_id="run-1",
        scope=scope,
        packets=[packet],
        evidence_entries=[],
        generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )

    assert brief.executive_summary == (
        "Declared-scope research produced 2 findings, 0 candidate claims, "
        "and 0 evidence records. Highest-confidence findings: "
        "Higher-confidence signal.; Lower-confidence signal. "
        "Conclusions are limited to the declared scope."
    )
```

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
python -m pytest \
  tests/unit/test_profile_registry.py::test_talent_profile_uses_renderer_v2_without_schema_version_change \
  tests/unit/test_talent_artifacts.py::test_talent_artifacts_are_deterministic_and_require_review_for_unknown_evidence \
  tests/unit/test_talent_artifacts.py::test_talent_summary_falls_back_to_ranked_findings_without_claims \
  -q
```

Expected: FAIL because the Talent renderer is still version `1` and the summary is count-only.

- [ ] **Step 4: Implement deterministic summary construction**

Add `Finding` and `Claim` to the imports from `agent.talent_contracts`, then add
these helpers below `_canonical_hash()` in `api/talent_artifacts.py`:

```python
def _count_label(count: int, singular: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {singular}{suffix}"


def _build_executive_summary(
    *,
    findings: list[Finding],
    claims: list[Claim],
    evidence_count: int,
) -> str:
    counts = (
        f"{_count_label(len(findings), 'finding')}, "
        f"{_count_label(len(claims), 'candidate claim')}, and "
        f"{_count_label(evidence_count, 'evidence record')}"
    )
    ranked_claims = sorted(claims, key=lambda item: (-item.confidence, item.claim_id))
    ranked_findings = sorted(
        findings, key=lambda item: (-item.confidence, item.finding_id)
    )
    if ranked_claims:
        signal_label = "Highest-confidence decision signals"
        signals = [item.text for item in ranked_claims[:3]]
    else:
        signal_label = "Highest-confidence findings"
        signals = [item.statement for item in ranked_findings[:3]]

    joined_signals = "; ".join(signals)
    terminal = "" if joined_signals.endswith((".", "!", "?", "。", "！", "？")) else "."
    signal_text = (
        f" {signal_label}: {joined_signals}{terminal}" if joined_signals else ""
    )
    return (
        f"Declared-scope research produced {counts}."
        f"{signal_text} Conclusions are limited to the declared scope."
    )
```

Replace the current count-only `executive_summary` assignment with:

```python
            executive_summary=_build_executive_summary(
                findings=findings,
                claims=claims,
                evidence_count=len(evidence),
            ),
```

Change only `TALENT_PROFILE.renderer_version` in `agent/profile_registry.py`:

```python
    renderer_version="2",
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_profile_registry.py tests/unit/test_talent_artifacts.py -q
```

Expected: PASS. Existing review triggers and deterministic artifact equality remain unchanged.

- [ ] **Step 6: Commit summary and version changes**

```bash
git add agent/profile_registry.py api/talent_artifacts.py \
  tests/unit/test_profile_registry.py tests/unit/test_talent_artifacts.py
git commit -m "feat(research): add evidence-bound brief summary"
```

### Task 2: Deterministic Decision Snapshot And Signal Tables

**Files:**
- Modify: `tests/unit/test_decision_brief.py`
- Modify: `api/decision_brief.py:1-48`

- [ ] **Step 1: Add rich contract fixtures to the renderer test**

Add these helpers below `_brief()` in `tests/unit/test_decision_brief.py`:

```python
def _finding(*, finding_id: str, statement: str, confidence: float):
    from agent.talent_contracts import Finding

    return Finding(
        finding_id=finding_id,
        research_question_id="question-1",
        statement=statement,
        evidence_refs=[f"ev-{finding_id}"],
        sample_scope="Five declared samples",
        confidence=confidence,
        evidence_gaps=[f"Gap for {finding_id}"],
        contradictions=[f"Contradiction for {finding_id}"],
        limitations=[f"Limit for {finding_id}"],
    )


def _claim(*, claim_id: str, text: str, confidence: float):
    from agent.talent_contracts import Claim

    return Claim(
        claim_id=claim_id,
        text=text,
        claim_type="hiring_signal",
        finding_refs=["finding-high"],
        evidence_refs=[f"ev-{claim_id}"],
        confidence=confidence,
        citation_status="cited",
        verification_status="unverified",
        review_status="pending",
        conflict_status="none",
        limitations=[f"Limit for {claim_id}"],
    )
```

- [ ] **Step 2: Write the failing complete-presentation test**

Add:

```python
def test_markdown_renderer_surfaces_complete_evidence_bound_contract():
    from api.decision_brief import render_markdown, with_content_hash

    brief = with_content_hash(
        _brief().model_copy(
            update={
                "renderer_version": "2",
                "findings": [
                    _finding(
                        finding_id="finding-low",
                        statement="Lower-confidence signal",
                        confidence=0.6,
                    ),
                    _finding(
                        finding_id="finding-high",
                        statement="Higher-confidence signal",
                        confidence=0.9,
                    ),
                ],
                "claims": [
                    _claim(claim_id="claim-low", text="Lower claim", confidence=0.5),
                    _claim(claim_id="claim-high", text="Higher claim", confidence=0.95),
                ],
                "conflicts": ["Declared conflict"],
                "review_summary": {
                    "status": "required",
                    "required_before_delivery": True,
                    "triggers": ["missing_evidence_ref:claim-high:ev-missing"],
                },
                "quality_summary": {
                    "finding_count": 2,
                    "claim_count": 2,
                    "evidence_count": 4,
                },
            }
        )
    )

    markdown = render_markdown(brief)

    assert "## Executive Snapshot" in markdown
    assert "| Findings | 2 |" in markdown
    assert "| Review status | required |" in markdown
    assert "| Delivery gate | Yes |" in markdown
    assert "## Capability Signal Matrix" in markdown
    assert markdown.index("Higher-confidence signal") < markdown.index(
        "Lower-confidence signal"
    )
    assert "`ev-finding-high`" in markdown
    assert "Gap for finding-high" in markdown
    assert "Contradiction for finding-high" in markdown
    assert "Limit for finding-high" in markdown
    assert "## Candidate Claims" in markdown
    assert markdown.index("Higher claim") < markdown.index("Lower claim")
    assert "cited / unverified / pending / none" in markdown
    assert "Limit for claim-high" in markdown
    assert "## Evidence Gaps" in markdown
    assert "## Review Triggers" in markdown
    assert "## Conflicts" in markdown
```

- [ ] **Step 3: Write failing safety and empty-state tests**

Add:

```python
def test_markdown_renderer_escapes_untrusted_table_content():
    from api.decision_brief import render_markdown, with_content_hash

    finding = _finding(
        finding_id="finding-high",
        statement="Signal | row\n<script>alert(1)</script>",
        confidence=0.9,
    )
    brief = with_content_hash(
        _brief().model_copy(
            update={
                "renderer_version": "2",
                "findings": [finding],
                "recommendations": [],
            }
        )
    )

    markdown = render_markdown(brief)

    assert "Signal \\| row<br>&lt;script&gt;alert(1)&lt;/script&gt;" in markdown
    assert "<script>" not in markdown
    assert "## Recommendations" not in markdown


def test_markdown_renderer_handles_empty_optional_sections():
    from api.decision_brief import render_markdown, with_content_hash

    brief = with_content_hash(
        _brief().model_copy(
            update={
                "renderer_version": "2",
                "findings": [],
                "claims": [],
                "conflicts": [],
                "recommendations": [],
                "review_summary": {},
                "quality_summary": {},
            }
        )
    )

    markdown = render_markdown(brief)

    assert markdown.count("_None declared_") == 2
    assert "| Findings | Not declared |" in markdown
    assert "| Review status | Not declared |" in markdown
    assert "## Evidence Gaps" not in markdown
    assert "## Review Triggers" not in markdown
    assert "## Conflicts" not in markdown
    assert "## Recommendations" not in markdown
```

- [ ] **Step 4: Run renderer tests and verify RED**

Run:

```bash
python -m pytest tests/unit/test_decision_brief.py -q
```

Expected: FAIL because the current renderer omits the snapshot and evidence-bound tables and does not escape table content.

- [ ] **Step 5: Implement the pure Markdown helpers**

Replace `api/decision_brief.py` with the existing canonical hash functions plus
the following presentation helpers and renderer:

```python
"""Canonical DecisionBrief hashing and deterministic Markdown rendering."""
from __future__ import annotations

from html import escape
import hashlib
import json
from typing import Any, Iterable

from agent.talent_contracts import Claim, DecisionBrief, Finding


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


def _ordered_unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _cell(value: Any) -> str:
    text = escape(str(value), quote=False)
    return (
        text.replace("`", "&#96;")
        .replace("|", r"\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _refs(items: Iterable[str]) -> str:
    refs = _ordered_unique(items)
    return "<br>".join(f"`{_cell(item)}`" for item in refs) or "None declared"


def _joined(items: Iterable[str]) -> str:
    values = _ordered_unique(items)
    return "<br>".join(_cell(item) for item in values) or "None declared"


def _bullets(items: Iterable[str]) -> str:
    values = list(items)
    return "\n".join(f"- {_cell(item)}" for item in values) if values else "- None declared"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None declared_"
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _snapshot_value(value: Any) -> str:
    if value is None:
        return "Not declared"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return _cell(value)


def _finding_rows(findings: list[Finding]) -> list[list[str]]:
    ranked = sorted(findings, key=lambda item: (-item.confidence, item.finding_id))
    return [
        [
            _cell(item.statement),
            _cell(item.sample_scope),
            f"{item.confidence:.0%}",
            _refs(item.evidence_refs),
            _joined([*item.evidence_gaps, *item.contradictions, *item.limitations]),
        ]
        for item in ranked
    ]


def _claim_rows(claims: list[Claim]) -> list[list[str]]:
    ranked = sorted(claims, key=lambda item: (-item.confidence, item.claim_id))
    return [
        [
            _cell(item.text),
            _cell(item.claim_type),
            f"{item.confidence:.0%}",
            _refs(item.finding_refs),
            _refs(item.evidence_refs),
            _cell(
                " / ".join(
                    [
                        item.citation_status,
                        item.verification_status,
                        item.review_status,
                        item.conflict_status,
                    ]
                )
            ),
            _joined(item.limitations),
        ]
        for item in ranked
    ]


def _list_value(mapping: dict[str, Any], key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def render_markdown(brief: DecisionBrief) -> str:
    """Render stable Markdown from canonical JSON; no model calls or file tools."""
    snapshot_rows = [
        ["Findings", _snapshot_value(brief.quality_summary.get("finding_count"))],
        [
            "Candidate claims",
            _snapshot_value(brief.quality_summary.get("claim_count")),
        ],
        [
            "Evidence records",
            _snapshot_value(brief.quality_summary.get("evidence_count")),
        ],
        ["Review status", _snapshot_value(brief.review_summary.get("status"))],
        [
            "Delivery gate",
            _snapshot_value(brief.review_summary.get("required_before_delivery")),
        ],
    ]
    sections = [
        "# Talent Hiring Signal Decision Brief\n\n"
        f"- Run ID: `{_cell(brief.run_id)}`\n"
        f"- Profile: `{_cell(brief.profile_id)}@{_cell(brief.profile_version)}`\n"
        f"- Content hash: `{_cell(brief.content_hash)}`\n"
        f"- Generated at: `{_cell(brief.generated_at.isoformat())}`",
        f"## Executive Summary\n\n{_cell(brief.executive_summary)}",
        "## Executive Snapshot\n\n"
        + _table(["Metric", "Value"], snapshot_rows),
        f"## Target Roles\n\n{_bullets(brief.scope.target_roles)}",
        "## Capability Signal Matrix\n\n"
        + _table(
            ["Signal", "Sample scope", "Confidence", "Evidence", "Boundaries"],
            _finding_rows(brief.findings),
        ),
        "## Candidate Claims\n\n"
        + _table(
            [
                "Claim",
                "Type",
                "Confidence",
                "Finding refs",
                "Evidence refs",
                "Status",
                "Boundaries",
            ],
            _claim_rows(brief.claims),
        ),
    ]

    evidence_gaps = _ordered_unique(
        gap for finding in brief.findings for gap in finding.evidence_gaps
    )
    if evidence_gaps:
        sections.append(f"## Evidence Gaps\n\n{_bullets(evidence_gaps)}")

    review_triggers = _list_value(brief.review_summary, "triggers")
    if review_triggers:
        sections.append(f"## Review Triggers\n\n{_bullets(review_triggers)}")
    if brief.conflicts:
        sections.append(f"## Conflicts\n\n{_bullets(brief.conflicts)}")

    sections.append(f"## Limitations\n\n{_bullets(brief.limitations)}")
    if brief.recommendations:
        sections.append(f"## Recommendations\n\n{_bullets(brief.recommendations)}")
    return "\n\n".join(sections) + "\n"
```

- [ ] **Step 6: Run renderer tests and verify GREEN**

Run:

```bash
python -m pytest tests/unit/test_decision_brief.py -q
```

Expected: PASS with stable ordering, complete evidence-bound sections, escaped input, and conditional empty sections.

- [ ] **Step 7: Run artifact regression tests**

Run:

```bash
python -m pytest tests/unit/test_talent_artifacts.py tests/unit/test_run_repository.py tests/integration/test_run_api.py -q
```

Expected: PASS. Artifact IDs, persistence, review behavior, and retrieval remain unchanged.

- [ ] **Step 8: Commit renderer changes**

```bash
git add api/decision_brief.py tests/unit/test_decision_brief.py
git commit -m "feat(research): render evidence-bound Talent snapshot"
```

### Task 3: Benchmark Runbook And Documentation Boundary

**Files:**
- Modify: `benchmarks/talent-hiring-signal-v1/README.md`
- Modify: `docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md`

- [ ] **Step 1: Add the renderer-v2 verification section**

Append a section to `benchmarks/talent-hiring-signal-v1/README.md` containing
these exact requirements:

````markdown
## Renderer v2 Readability Check

The renderer-v2 check evaluates presentation over the existing evidence-bound
Talent contract. It does not ask the model for JD edits, interview questions,
or new recommendations.

Run a 1x2 diagnostic first:

```bash
python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 1 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-1x2.json
```

Only continue to 3x2 when the diagnostic reports two completed runs,
`ready_for_human_review=true`, and zero Talent readiness failure counters.

```bash
python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-3x2.json
```

For each Talent `decision-brief.md`, verify that the executive snapshot,
capability matrix, candidate claims, evidence refs, and declared boundaries are
visible without opening the JSON artifact. This is a readability regression
check, not a new claim about the wider hiring market.
````

- [ ] **Step 2: Retain the approved design correction**

Verify the source spec includes both:

```markdown
| Boundaries | `Claim.limitations` |
```

and the requirement to render `review_summary.triggers` conditionally. Do not
change any other approved scope.

- [ ] **Step 3: Verify documentation**

Run:

```bash
git diff --check
rg -n "Renderer v2 Readability Check|JD edits|review_summary.triggers" \
  benchmarks/talent-hiring-signal-v1/README.md \
  docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md
```

Expected: `git diff --check` exits 0 and all three boundary markers are found.

- [ ] **Step 4: Commit documentation**

```bash
git add benchmarks/talent-hiring-signal-v1/README.md \
  docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md
git commit -m "docs(benchmark): define Talent renderer v2 gate"
```

### Task 4: Full Regression And Fixed Benchmark Gate

**Files:**
- Review all branch changes.
- Create benchmark outputs only under `/tmp`; do not commit them.

- [ ] **Step 1: Run all focused tests**

Run:

```bash
python -m pytest \
  tests/unit/test_decision_brief.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full backend suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass. Record the actual count and warnings; do not reuse a prior count.

- [ ] **Step 3: Run static and diff checks**

Run:

```bash
python -m compileall -q api/decision_brief.py api/talent_artifacts.py
git diff --check origin/main...HEAD
```

Expected: both commands exit 0.

- [ ] **Step 4: Run the configured 1x2 diagnostic**

Resolve the primary checkout's untracked `.env` without printing values. This
keeps credentials outside the linked worktree and passes them only to the
benchmark child process:

```bash
PRIMARY_REPO="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
ENV_FILE="$PRIMARY_REPO/.env"
test -f "$ENV_FILE"
python -m dotenv -f "$ENV_FILE" run -- python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 1 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-1x2.json
```

Inspect only the allowlisted completion/artifact fields. Required result:

- `expected_run_count=2`
- `completed_run_count=2`
- `ready_for_human_review=true`
- all Talent schema, evidence, evidence-ref, artifact, disallowed-tool, timeout,
  recursion, profile, and identity failure counters are `0`
- Talent artifacts include `decision-brief.json` and `decision-brief.md`
- the JSON artifact declares `renderer_version="2"`

If any requirement fails, stop before 3x2 and use `superpowers:systematic-debugging`.

- [ ] **Step 5: Run the configured 3x2 gate**

Run:

```bash
python -m dotenv -f "$ENV_FILE" run -- python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-3x2.json
```

Required result:

- `expected_run_count=6`
- `completed_run_count=6`
- `ready_for_human_review=true`
- all Talent readiness failure counters remain `0`
- all three Talent Markdown artifacts contain the renderer-v2 snapshot, matrix,
  claims, evidence refs, and declared boundaries

This gate proves output stability and reviewability on the fixed declared
sample. It does not repeat or enlarge the already approved P1A market-value
claim.

- [ ] **Step 6: Review branch diff against the source spec**

Run:

```bash
git status --short
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- \
  agent/profile_registry.py \
  api/decision_brief.py \
  api/talent_artifacts.py \
  tests/unit/test_decision_brief.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_profile_registry.py \
  benchmarks/talent-hiring-signal-v1/README.md \
  docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md
```

Expected: no files outside the approved scope, no new dependencies, no model or
prompt changes, no schema/API/database/frontend changes, and a clean worktree
after all commits.

### Task 5: Pre-Landing Review And Handoff

**Files:**
- Review the complete branch diff and actual verification output.

- [ ] **Step 1: Run `gstack-review` lightly**

Focus the review on:

- Markdown/HTML injection and delimiter escaping;
- deterministic ordering and content-hash version semantics;
- accidental promotion of pending/unverified claims;
- preservation of artifact IDs, review authority, and readiness gates;
- exact scope adherence.

Fix only actionable findings inside this plan's scope, rerun affected focused
tests, then rerun the full suite if runtime code changes.

- [ ] **Step 2: Run verification-before-completion**

Use `superpowers:verification-before-completion` with fresh command output for:

- source spec coverage;
- implementation plan coverage;
- complete branch diff;
- focused and full tests;
- 1x2 and 3x2 result counters;
- documentation impact.

- [ ] **Step 3: Prepare the delivery summary**

Report:

- branch and worktree path;
- commits created;
- actual focused/full test counts;
- 1x2 and 3x2 completion/readiness counters;
- renderer-v2 artifact behavior;
- compatibility and rollback boundary;
- any deferred taxonomy/JD/interview work.

Do not push or create a PR until the user explicitly approves those external
actions.
