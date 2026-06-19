# Talent DecisionBrief Readability Design

## Goal

Make the canonical Talent Hiring Signal `decision-brief.md` scannable within
two minutes without weakening its evidence contract, changing review authority,
or asking the model for additional output.

This is a benchmark-bounded presentation milestone. It does not establish
market-wide accuracy, production adoption, or product-market fit.

## Evidence And Problem Statement

The fixed P1A benchmark showed that `talent-hiring-signal` was stronger than
`generic` on action value, evidence constraint, and hiring decision support
without increasing boundary risk. Generic output was easier to scan in some
paired reviews. The current Markdown artifact also omits findings, claims,
evidence references, review state, conflicts, and evidence gaps that already
exist in the canonical `DecisionBrief`.

The missing capability is deterministic presentation, not additional research,
reasoning, or advice generation.

## Decision

Add a renderer-v2 presentation layer over the existing `DecisionBrief`:

- keep `ResearchScope`, `ResearchPacket`, `Finding`, `Claim`, `ReviewBundle`,
  and `DecisionBrief` schemas unchanged;
- keep canonical hashing, artifact IDs, persistence, API routes, and review
  authority unchanged;
- show a bounded first-read snapshot containing only findings whose non-empty
  evidence refs all resolve to verified, unambiguous evidence records;
- preserve canonical finding order after eligibility filtering and display at
  most three snapshot findings;
- keep candidate claims out of the snapshot, regardless of confidence or their
  current verification status;
- render unresolved findings, every candidate claim, gaps, conflicts,
  limitations, and complete finding/claim appendices deterministically;
- render recommendations only when the canonical brief already contains them.

`confidence` remains model metadata. It is displayed in detail blocks but is
not a business-priority score and does not control placement.

## Non-Goals

This change does not:

- alter Talent prompts, tools, structured output, filesystem policy, or model
  calls;
- add JD edits, interview questions, candidate evaluation, or other hiring
  advice;
- add an LLM reviewer or make LangSmith a business record;
- change `ResearchRun`, `EvidenceLedger`, review, database, API, or persistence
  schemas;
- add Skills, Async Subagents, durable HITL, UI, ATS, email, or dashboard work;
- migrate or rerender existing renderer-v1 artifacts.

## Architecture

```text
ResearchPacket + EvidenceLedger snapshot
                 |
                 v
       build_talent_artifacts()
                 |
                 v
         canonical DecisionBrief
                 |
          +------+------+
          |             |
          v             v
  decision-brief.json   renderer v2
  unchanged schema      decision-brief.md
                        - bounded snapshot
                        - needs verification
                        - complete appendices
```

`api/talent_artifacts.py` continues to construct the canonical brief.
`api/review_service.py` continues to own review status. The renderer in
`api/decision_brief.py` derives presentation-only placement and cannot change
delivery or review decisions.

## Snapshot Eligibility

A finding is eligible only when all conditions hold:

1. it declares at least one evidence ref;
2. every ref resolves to exactly one `evidence_summary` entry;
3. every resolved entry has `verification_status="verified"`;
4. the finding has no contradictions;
5. the brief has no global conflicts.

Malformed evidence records, empty or unhashable IDs, unknown statuses, and
duplicate IDs fail closed. Every occurrence of a duplicate ID is ambiguous and
excluded from the verified index.

Global conflicts block every snapshot finding because the current brief no
longer retains finding-level ownership for packet contradictions. Candidate
claims never enter the snapshot in renderer v2 because the contract still
labels them as candidates and durable approval is not enabled.

## Information Hierarchy

```text
1. Decision Snapshot
   - declared scope and record counts
   - exact ReviewBundle status
   - separate presentation-only snapshot eligibility
   - at most three eligible findings in canonical order
2. Scope And Coverage
3. Needs Verification
4. Evidence Gaps And Conflicts
5. Limitations
6. Detailed Findings Appendix
7. Candidate Claims Appendix
8. Artifact Metadata
9. Recommendations, only when already present
```

The snapshot is the only Markdown table and has two columns. Long content uses
vertical labeled blocks. All findings and claims remain in appendices without
silent truncation.

## Empty And Degraded States

| Condition | Required display |
|---|---|
| No findings | `No findings are present in this brief.` |
| No eligible finding | `No verified evidence-backed findings are available for the snapshot.` |
| No evidence records | Same fail-closed state plus `Evidence records: 0` |
| Missing/unverified ref | Finding appears under `Needs Verification` and appendix only |
| Candidate claim | Appears under `Needs Verification` and appendix only |
| Unknown optional summary value | `Not declared`; no truthy coercion |
| No recommendations | Recommendations section omitted |

`Review bundle status` is rendered from `review_summary.status`. Snapshot
eligibility is explicitly presentation-only; `not_required` is never expanded
into a claim that human review is unnecessary.

## Markdown Safety

All source/model text is untrusted. Before rendering, the renderer:

1. normalizes CR/LF and Unicode line separators;
2. removes non-printing control and formatting characters;
3. HTML-escapes `<`, `>`, `&`, and quotes;
4. escapes Markdown structural characters;
5. converts normalized embedded line breaks to renderer-owned `<br>` tokens.

The renderer does not emit source-provided HTML, links, or images. Evidence
URLs are not converted into clickable Markdown.

## Versioning And Compatibility

- Talent `renderer_version` changes from `1` to `2`.
- `brief_schema_version` remains `1`.
- `canonicalization_version` remains `1`.
- `content_hash` remains the canonical semantic hash shared by JSON and
  Markdown artifacts; it is not an artifact-byte checksum.
- `generated_at` remains excluded from the semantic hash, so timestamp-only
  changes can change Markdown bytes without changing `content_hash`.
- Artifact IDs remain `decision-brief.json` and `decision-brief.md`; kinds,
  media types, API routes, and persistence records remain compatible.
- Stored renderer-v1 artifacts are immutable and are not migrated.

Renderer code and `renderer_version="2"` deploy and roll back together.

## Runner Contract

The value-gate runner validates Talent artifacts before export sanitization. A
Talent run passes the renderer contract only when:

- exactly one expected JSON artifact and one expected Markdown artifact exist;
- each has the expected ID, kind, media type, non-empty content, and declared
  semantic hash;
- JSON validates as `DecisionBrief` with `renderer_version="2"`;
- recomputed semantic hash matches the brief and both artifact declarations;
- Markdown equals `render_markdown(parsed_brief)` byte-for-byte.

Any failure increments `renderer_contract_failure_count` and prevents
`ready_for_human_review=true`. The CLI still writes and prints the diagnostic
bundle path, then exits `1` for an incomplete benchmark.

## File-Level Scope

| File | Change |
|---|---|
| `api/decision_brief.py` | Pure renderer-v2 helpers and presentation |
| `agent/profile_registry.py` | Talent `renderer_version="2"` only |
| `scripts/talent_value_gate_runner.py` | Fail-closed renderer contract gate |
| `tests/unit/test_decision_brief.py` | Eligibility, safety, empty-state, and golden tests |
| `tests/unit/test_profile_registry.py` | Version contract |
| `tests/unit/test_talent_artifacts.py` | Artifact identity/version regression |
| `tests/unit/test_talent_value_gate_runner.py` | Corrupt artifact and CLI exit tests |
| `tests/unit/test_run_repository.py` | Finalize/retrieve byte compatibility |
| `tests/fixtures/talent-decision-brief-renderer-v2.*` | Canonical input and byte-exact Markdown |
| `benchmarks/talent-hiring-signal-v1/README.md` | Deterministic, independent readability, and live gates |
| `benchmarks/talent-hiring-signal-v1/renderer-v2-readability-scorecard.md` | Timed AI-assisted independent gate |
| `benchmarks/talent-hiring-signal-v1/renderer-v2-readability-answer-key.md` | Separate post-timer scoring key |

No contract, review-service, database, API, frontend, prompt, or model file is
in scope.

## Validation Sequence

1. Run focused renderer/profile/artifact/runner tests.
2. Run persistence and retrieval integration tests.
3. Run the complete backend suite and compile checks.
4. Complete the fixed golden Markdown scorecard in a fresh read-only AI session
   recorded as `ai-assisted-independent-reviewer`; require 5/5 within 120
   seconds and keep the answer key separate until timing stops.
5. Run the fixed 1x2 live regression. Stop on any counter failure.
6. Run 3x2 only after 1x2 is ready.

Live runs verify end-to-end stability, not readability or broader market value.

## Acceptance Criteria

1. The snapshot contains only eligible findings, preserves canonical order, and
   displays at most three.
2. Candidate claims never enter the snapshot.
3. Complete findings and claims remain available in appendices.
4. Hostile HTML, Markdown, control characters, and line separators cannot
   inject structure.
5. Talent artifacts declare renderer v2 while schema/canonicalization remain v1.
6. Golden bytes, focused tests, full backend tests, and persistence checks pass.
7. The timed AI-assisted independent reviewer scores 5/5 within 120 seconds;
   owner confirmation remains a brief final delivery check, not a second timed
   benchmark gate.
8. Fixed 1x2 and 3x2 runs are ready with every readiness counter, including
   `renderer_contract_failure_count`, equal to zero.

## Rollback

Revert `api/decision_brief.py` and restore Talent `renderer_version="1"` in the
same deployment. Do not delete or rerender already persisted renderer-v2
artifacts. No data or API migration is required.

## Deferred Work

- A separately versioned presentation schema after a second consumer exists.
- Input/list hard limits approved as a schema decision, not renderer truncation.
- Evidence-bound JD, interview, and candidate-evaluation policies.
- UI/ATS/email/dashboard adapters and persona-specific prioritization.
- P1B durable HITL, Skills, Async Subagents, and LLM review.
