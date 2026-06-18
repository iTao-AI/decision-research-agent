# Talent DecisionBrief Readability Design

## Goal

Make the canonical Talent Hiring Signal `DecisionBrief` faster for an HR or
hiring lead to scan without weakening its evidence contract or asking the model
for additional output.

This iteration improves deterministic presentation only. It does not generate
JD edits, interview questions, or other recommendations that are not already
supported by the current structured research contract.

## Evidence And Problem Statement

The P1A value gate passed: the `talent-hiring-signal` profile was stronger than
the `generic` profile on action value, evidence constraint, and hiring decision
support without increasing boundary risk. Reviewers still found the generic
profile easier to scan in some comparisons, especially when it used a compact
summary matrix.

The current canonical artifact underuses data that already exists:

- `DecisionBrief` persists evidence-bound findings and candidate claims.
- `render_markdown()` renders only metadata, a count-based executive summary,
  target roles, limitations, and an empty recommendations section.
- Findings, claims, evidence references, confidence, review state, conflicts,
  and evidence gaps are absent from the Markdown artifact.

The missing capability is therefore presentation, not research or agent
reasoning.

## Decision

Add an evidence-preserving deterministic presentation layer over the existing
`DecisionBrief` fields.

- Keep `ResearchScope`, `ResearchPacket`, `Finding`, `Claim`, `ReviewBundle`,
  and `DecisionBrief` schemas unchanged.
- Keep the current deterministic artifact service and content hashing model.
- Build a concise executive summary from existing counts and the highest
  confidence candidate claims.
- Render all findings in a capability signal matrix with their declared scope,
  confidence, evidence references, and boundaries.
- Render all candidate claims with their finding/evidence references and review
  state.
- Render conflicts, evidence gaps, limitations, and recommendations only from
  fields already present in the canonical brief.
- Do not make model calls, read files, use tools, or infer new hiring advice in
  the renderer.

## Non-Goals

This change does not:

- alter Talent agent prompts, tools, structured output, or filesystem policy;
- add JD rewrite advice, interview questions, or candidate evaluation logic;
- add an LLM reviewer or use LangSmith as a business record;
- change `ResearchRun`, `EvidenceLedger`, review, persistence, or API schemas;
- add Skills, Async Subagents, durable HITL, or UI work;
- change the `generic` profile or rerun P1A to justify a broader product claim.

## Options Considered

### Option A: Deterministic Presentation Over Existing Contracts

Use existing findings, claims, evidence references, and limitations to build a
compact Markdown decision snapshot.

Selected because it directly addresses the observed readability gap with the
smallest blast radius and no new trust boundary.

### Option B: Extend `DecisionBrief` With A Capability Matrix Schema

Persist a new structured matrix and additional hiring-decision fields.

Rejected for this iteration because the matrix can be rendered losslessly from
existing canonical fields. A schema/version migration would add no new factual
content.

### Option C: Ask The Talent Model For JD And Interview Recommendations

Extend `ResearchPacket` and structured output prompts with recommendations.

Rejected because the current contract has no stable taxonomy for mapping hiring
signals to JD edits or interview questions. This would increase structured
output failure risk and allow unsupported advice to appear authoritative.

## Architecture

```text
ResearchPacket + EvidenceLedger snapshot
                 |
                 v
       build_talent_artifacts()
                 |
        existing canonical fields
                 |
       +---------+----------+
       |                    |
       v                    v
DecisionBrief JSON    deterministic Markdown renderer v2
unchanged schema      - executive snapshot
                      - capability signal matrix
                      - candidate claims
                      - evidence gaps / conflicts
                      - limitations
```

`api/talent_artifacts.py` remains responsible for constructing the canonical
brief. `api/decision_brief.py` remains responsible for canonical hashing and
Markdown presentation. Pure helper functions may be added to those modules, but
no new service or persistence layer is introduced.

## Deterministic Presentation Policy

### Stable Ordering

Presentation row order must not depend on model emission order when a semantic
priority is available. Canonical JSON preserves the existing list-order
semantics, so reordering canonical input may still produce a different content
hash even when the rendered table rows have the same semantic order.

- Candidate claims: descending `confidence`, then ascending `claim_id`.
- Findings: descending `confidence`, then ascending `finding_id`.
- Text within each row remains exactly the contract-provided text after Markdown
  escaping. The renderer does not paraphrase it.
- Evidence references retain their declared order after duplicate removal.
- Boundaries retain first-seen order after duplicate removal.

Stable tie-breakers are required so equivalent canonical inputs produce
byte-stable Markdown.

### Executive Summary

Replace the current count-only summary with a deterministic summary containing:

1. finding, candidate claim, and evidence counts;
2. up to three highest-confidence candidate claim texts;
3. if no claims exist, up to three highest-confidence finding statements;
4. an explicit statement that conclusions are limited to the declared scope.

The summary reuses contract text verbatim. It does not synthesize a new claim.
All omitted items remain visible in later sections.

### Executive Snapshot

Render a compact table before detailed content:

| Metric | Source |
|---|---|
| Findings | `quality_summary.finding_count` |
| Candidate claims | `quality_summary.claim_count` |
| Evidence records | `quality_summary.evidence_count` |
| Review status | `review_summary.status` |
| Delivery gate | `review_summary.required_before_delivery` |

Missing optional dictionary keys render as `Not declared`; they do not cause an
artifact failure.

### Capability Signal Matrix

Render one row for every finding:

| Column | Canonical source |
|---|---|
| Signal | `Finding.statement` |
| Sample scope | `Finding.sample_scope` |
| Confidence | `Finding.confidence` formatted as a percentage |
| Evidence | `Finding.evidence_refs` |
| Boundaries | ordered union of `evidence_gaps`, `contradictions`, and `limitations` |

The matrix must not label a signal as common, universal, required, or
scene-specific unless that classification already appears in contract text.
This prevents the presentation layer from introducing a stronger market claim.

### Candidate Claims

Render one row for every claim:

| Column | Canonical source |
|---|---|
| Claim | `Claim.text` |
| Type | `Claim.claim_type` |
| Confidence | `Claim.confidence` formatted as a percentage |
| Finding refs | `Claim.finding_refs` |
| Evidence refs | `Claim.evidence_refs` |
| Status | citation, verification, review, and conflict status |
| Boundaries | `Claim.limitations` |

This section remains explicitly labeled as candidate claims. Rendering does not
promote a pending or unverified claim to an approved decision.

### Boundaries And Recommendations

- Aggregate finding evidence gaps into an `Evidence Gaps` section.
- Render `review_summary.triggers` in a `Review Triggers` section when present.
- Render brief-level `conflicts` and `limitations` in separate sections.
- Render `Recommendations` only when `brief.recommendations` is non-empty.
- An empty recommendations list produces no recommendations section and is not
  replaced with generated advice.

### Markdown Safety

All table-cell text must HTML-escape model-provided content, escape pipe
characters, and then normalize embedded line breaks to renderer-owned `<br>`
separators. Evidence IDs remain code-formatted. The renderer must not emit raw
HTML supplied by model-provided text.

## Versioning And Compatibility

- Increment the Talent profile `renderer_version` from `1` to `2`.
- Keep `brief_schema_version="1"` because no fields or validation rules change.
- Keep `canonicalization_version="1"` because the canonical JSON hashing
  algorithm does not change.
- The improved `executive_summary` and renderer version intentionally change the
  canonical content hash for newly built artifacts.
- Existing persisted artifacts are immutable and are not rewritten.
- Artifact IDs, media types, API routes, and persistence records remain
  compatible.

## Data Flow And Failure Behavior

1. The final validated `ResearchPacket` and evidence snapshot enter
   `build_talent_artifacts()` as they do today.
2. The artifact service deterministically builds the improved executive summary
   and otherwise preserves all existing canonical fields.
3. `with_content_hash()` hashes the canonical JSON with the same exclusions and
   canonicalization rules as today.
4. `render_markdown()` renders the v2 presentation from the hashed brief.
5. Persistence stores the same two artifact kinds atomically.

Empty findings or claims do not crash rendering. The relevant table renders a
short `None declared` message, while existing review and benchmark gates retain
authority over whether the run is deliverable. The renderer never changes a
review decision.

## File-Level Scope

| File | Change |
|---|---|
| `api/decision_brief.py` | Add deterministic sorting, escaping, snapshot, matrix, claims, and boundary rendering helpers. |
| `api/talent_artifacts.py` | Build the evidence-bound executive summary from existing brief inputs. |
| `agent/profile_registry.py` | Increment Talent `renderer_version` to `2`. |
| `tests/unit/test_decision_brief.py` | Lock byte stability, ordering, Markdown escaping, complete matrix/claim rendering, and empty-section behavior. |
| `tests/unit/test_talent_artifacts.py` | Lock deterministic summary content and unchanged contract/review behavior. |
| `tests/unit/test_profile_registry.py` | Lock the renderer version increment without changing other profile contracts. |
| `benchmarks/talent-hiring-signal-v1/README.md` | Document the v2 readability verification procedure and evidence boundary. |

No API, database, frontend, Agent prompt, or tool files are in scope.

## Test Matrix

| Scenario | Expected result |
|---|---|
| Identical complete brief input | Byte-identical Markdown and content hash. |
| Findings/claims supplied in different orders | Confidence-first, ID-tied table rows; canonical hash retains existing input-order semantics. |
| Pipe/newline in contract text | Valid table cells without column injection or raw HTML. |
| More than three claims | Summary contains only the top three; all claims remain in the detailed table. |
| No claims | Summary falls back to top findings and claims section says `None declared`. |
| No recommendations | Recommendations section is absent. |
| Evidence gaps/review triggers/conflicts/limitations | Each appears only in its corresponding evidence-bound section or table column. |
| Pending/unverified claim | Status remains visible; renderer does not promote it. |
| Persisted artifact integration | Existing JSON/Markdown artifact IDs and hashes remain queryable. |
| Fixed 1x2 diagnostic | Both runs complete and Talent readiness counters remain zero. |
| Fixed 3x2 benchmark | Six runs complete, Talent remains review-ready, and no evidence/boundary counter regresses. |

## Validation Sequence

1. Run focused unit tests for decision brief rendering, Talent artifacts, and
   profile registry.
2. Run the full backend suite.
3. Run the frontend build only if the final diff unexpectedly touches frontend
   or public artifact display behavior; otherwise record it as not required.
4. Run the fixed 1x2 diagnostic benchmark with configured credentials.
5. If 1x2 remains review-ready, run the fixed 3x2 benchmark.
6. Review the three Talent Markdown artifacts for scanability against the prior
   P1A output. This is a presentation acceptance check, not a new market-value
   claim.

## Acceptance Criteria

1. A reviewer can see the highest-confidence signals, complete finding matrix,
   candidate claims, evidence references, and boundaries without opening raw
   JSON.
2. Every displayed statement and classification comes from the existing
   `DecisionBrief`; the renderer introduces no new factual or hiring advice.
3. `ResearchPacket`, `DecisionBrief`, review, API, and persistence schemas remain
   unchanged.
4. Talent artifacts declare `renderer_version="2"`; schema and canonicalization
   versions remain `1`.
5. Rendering is byte-stable for equivalent inputs and safe for Markdown table
   delimiters and line breaks.
6. Focused tests and the full backend suite pass.
7. Fixed 1x2 and 3x2 benchmark runs remain `ready_for_human_review` with all
   Talent readiness failure counters at zero.
8. Existing persisted artifacts are not migrated or rewritten.

## Rollback

Revert the renderer and summary changes and restore Talent
`renderer_version="1"`. No data migration or API rollback is required because
existing artifacts are immutable and the schema is unchanged.

## Deferred Work

- A stable taxonomy for mapping evidence-bound signals to JD recommendations.
- Evidence-bound interview verification prompts.
- UI-specific rendering of the same canonical artifact.
- P1B durable HITL and delivery approval workflow.
