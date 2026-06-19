<!-- /autoplan restore point: /Users/mac/.gstack/projects/iTao-AI-decision-research-agent/main-autoplan-restore-20260619-000129.md -->
# Talent DecisionBrief Readability Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans`. Implement each task with TDD and preserve the
> evidence boundary defined below.

**Status:** APPROVED - /autoplan completed 2026-06-19.

**Goal:** Make the canonical Talent `decision-brief.md` scannable within two
minutes without promoting unverified content, changing research contracts, or
adding new hiring advice.

**Architecture:** Keep `ResearchPacket`, `DecisionBrief`, review, persistence,
API, and model behavior unchanged. `api/decision_brief.py` derives a bounded
presentation layer from the canonical brief, renders eligible evidence-backed
findings first, places all unresolved material in a separate verification
section, and retains the complete contract in appendices. `renderer_version=2`
marks the presentation change; `schema_version` and
`canonicalization_version` remain `1`.

**Source spec:**
`docs/superpowers/specs/2026-06-18-talent-decision-brief-readability-design.md`

---

## Confirmed Premises

The owner selected the refined premise set at the `/autoplan` D1 gate.

1. P1A already demonstrated value only inside the fixed five-sample benchmark;
   this phase addresses the observed readability weakness and does not claim
   product-market fit or production adoption.
2. The direct fix is deterministic presentation. No new model calls, prompts,
   schema fields, Skills, Async Subagents, HITL, UI, JD advice, or interview
   advice are added.
3. The first reading layer may contain only evidence-backed findings. Pending,
   unverified, conflicting, or missing-reference claims remain visibly separate.
4. Readability requires a byte-exact golden fixture and one timed,
   independently executed AI-assisted rubric. Owner confirmation is a brief
   final delivery check. Live 1x2 and 3x2 runs are end-to-end regression gates
   only.
5. Markdown remains the canonical audit artifact for this phase, not the final
   ATS, dashboard, email, or product UI.
6. `executive_summary` remains human-readable display text and must not be
   parsed as a stable machine contract. Structured consumers use canonical
   fields; `renderer_version=2` signals changed presentation semantics.

### Stakes If These Premises Are Wrong

If presentation is not the actual bottleneck, this phase will produce a cleaner
artifact without improving downstream decisions. The bounded golden and human
gate limit that cost. Expanding now into advice generation or workflow UI would
create a larger evidence and delivery surface before the current milestone is
stable, so those directions remain deferred.

---

## Phase 1: CEO Review

### Premise Challenge

The original plan correctly targeted the only dimension that sometimes lost in
the completed blind review: reading efficiency. It incorrectly assumed that
model confidence was equivalent to business priority and allowed unverified
candidate claims to appear as “decision signals.” The revised plan keeps the
milestone but removes that semantic promotion and adds an explicit human
readability measure.

The external reviews also challenged the lack of market validation and product
workflow adoption. Those are valid 12-month questions but not blockers for this
portfolio milestone because P1A is explicitly benchmark-bounded. The plan now
states that boundary rather than introducing user-adoption work by implication.

### What Already Exists

| Sub-problem | Existing authority | Reuse decision |
|---|---|---|
| Canonical contract | `agent/talent_contracts.py::DecisionBrief` | Keep unchanged |
| Evidence verification state | `DecisionBrief.evidence_summary` | Derive display eligibility defensively |
| Claim review state | `Claim` and `review_summary` | Keep authority server-side; render only |
| Deterministic review | `api/review_service.py` | Do not duplicate or weaken rules |
| Canonical hashing | `api/decision_brief.py::with_content_hash` | Keep; renderer bump changes canonical hash through version |
| Artifact assembly | `api/talent_artifacts.py` | Keep behavior; only consumes renderer v2 through profile version |
| Profile version contract | `agent/profile_registry.py` | Change only `renderer_version` |
| End-to-end regression | `scripts/talent_value_gate_runner.py` | Reuse 1x2 then 3x2 |
| Benchmark boundary | `benchmarks/talent-hiring-signal-v1/README.md` | Extend with renderer-v2 runbook |

### Dream-State Delta

```text
CURRENT
  canonical JSON + minimal Markdown + long undifferentiated limitations
      |
      v
THIS PLAN
  bounded evidence-backed reading layer
  + explicit needs-verification layer
  + complete deterministic appendices
  + golden and timed readability gates
      |
      v
12-MONTH IDEAL (not in this phase)
  role-aware decision workspace
  + separately versioned presentation schema
  + ATS/dashboard/email delivery adapters
  + durable review workflow and measured user outcomes
```

This plan reaches a trustworthy audit artifact, not the 12-month product UI.
The remaining delta is workflow integration, persona-specific views, and
validated action guidance. Those require new evidence and contracts rather than
renderer logic.

### Implementation Alternatives

| Approach | Effort | Risk | Advantages | Decision |
|---|---:|---:|---|---|
| A. Deterministic renderer over current contract | Small | Low | Directly fixes known gap; no new authority | **Selected** |
| B. Add presentation schema to `DecisionBrief` | Medium | Medium | Better future UI contract | Deferred until multiple consumers require it |
| C. Generate hiring actions with an LLM | Large | High | More immediately actionable | Rejected for this phase; exceeds evidence boundary |

### Mode And Temporal Interrogation

Mode is **SELECTIVE EXPANSION**: preserve the approved scope, expand only the
verification and trust semantics needed to make it safe. In hour one the
implementation should establish RED tests for eligibility, empty states, and
golden bytes. By hour six the renderer, profile version, focused tests, and
documentation should be complete; model-backed regression runs happen only
after deterministic tests pass.

If the work grows beyond one small runtime module, one profile constant, tests,
fixtures, and benchmark documentation, stop and re-evaluate scope. Do not solve
future ATS/UI or recommendation-generation needs inside renderer helpers.

### CEO Review Sections

1. **Problem and outcome:** The known outcome is faster comprehension of an
   already evidence-governed artifact. The plan now avoids claiming adoption or
   market validation and defines a timed outcome instead of a cosmetic one.
2. **User and journey:** The immediate reader is an HR/recruiting reviewer
   inspecting a bounded market-intelligence brief. They must identify scope,
   usable findings, review state, and caveats without opening JSON.
3. **Error and rescue:** Missing or unverified evidence fails closed into an
   explicit empty or verification state. The renderer never fabricates a signal
   or changes the review authority.
4. **Scope:** The runtime scope is deliberately narrow and uses existing
   ownership boundaries. The only expansion accepted by autoplan is golden plus
   independent AI-assisted readability validation plus brief owner
   confirmation.
5. **Value:** P1A's blind review established stronger evidence constraint and
   decision support, while generic output sometimes scanned faster. This plan
   addresses that measured weakness without repeating the value experiment.
6. **Competition:** A static Markdown artifact is not positioned as a competitor
   to ATS platforms. Its differentiator for this milestone is deterministic,
   traceable, reviewable output.
7. **Trust:** Confidence is retained as model metadata, never used alone as a
   business priority. Verification, reference resolution, review state, and
   conflicts control placement.
8. **Delivery:** Deterministic tests precede paid/noisy model runs. Failure at
   1x2 blocks 3x2 and produces a concrete diagnostic path.
9. **Compatibility:** Existing schema and artifact IDs remain unchanged. Old
   artifacts remain renderer v1 and are not silently rerendered.
10. **Six-month trajectory:** The renderer remains a presentation adapter, not a
    hidden business-rules service. A future structured presentation contract is
    deferred until a second consumer proves the need.
11. **Design:** The artifact uses progressive disclosure: bounded summary,
    unresolved material, then complete appendices. This is reviewed in Phase 2.

### CEO Dual Voices

Claude independently challenged product/adoption evidence, missing human
readability measurement, and `executive_summary` compatibility. Codex
independently found trust-semantic errors, confidence-only ranking, unbounded
tables, and the mismatch between live benchmark cost and deterministic renderer
validation. Both supported a bounded deterministic renderer once those issues
were corrected.

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Premises valid | Partial | Partial | Confirmed after D1 revision |
| Right problem | Partial | Partial | Confirmed as benchmark-bounded |
| Scope calibration | Yes | Yes | Confirmed |
| Alternatives explored | Partial | Partial | Confirmed after alternatives table |
| Competitive/market risks | Flagged | Flagged | Deferred, explicitly bounded |
| Six-month trajectory | Flagged adoption risk | Flagged renderer-rule risk | Confirmed after boundary correction |

**Phase 1 result:** 12 Codex concerns and 8 Claude concerns were evaluated.
The owner confirmed the refined premises; no unresolved user challenge remains.

---

## Phase 2: Design Review

### Design Scope

This is document information design, not frontend visual design. No loading or
interaction state exists; the relevant states are verified, unresolved,
conflicting, missing evidence, empty results, and review required. Initial plan
completeness was 5/10 because it specified content but not trustworthy hierarchy
or human validation.

No repository `DESIGN.md` governs Markdown output. Existing project conventions
favor deterministic plain text, explicit evidence boundaries, and stable
artifacts. The revised structure follows those patterns and avoids renderer-
specific HTML beyond escaped text.

### Required Information Hierarchy

```text
# Talent Hiring Signal Decision Brief

1. Decision Snapshot
   - declared scope
   - record counts, labeled as counts rather than quality scores
   - review bundle status, rendered exactly as server authority
   - snapshot eligibility state, explicitly presentation-only
   - up to 3 eligible evidence-backed findings in canonical order
   - explicit no-eligible-findings state

2. Scope And Coverage
   - target roles, companies, time window, declared sample count/types

3. Needs Verification
   - all pending/unverified/conflicting/missing-reference claims and findings
   - status and references shown explicitly

4. Evidence Gaps And Conflicts

5. Limitations

6. Detailed Findings Appendix
   - every finding, no truncation

7. Candidate Claims Appendix
   - every claim, no truncation; candidate status remains explicit

8. Artifact Metadata
   - run/profile/version/hash/timestamp

9. Recommendations
   - render only when already present; renderer never invents them
```

### Placement Eligibility

A finding is eligible for the bounded snapshot only when it has at least one
evidence ref, every evidence ref
resolves to an `evidence_summary` entry whose `verification_status` is
`verified`, the finding has no contradiction, and `brief.conflicts` is empty.
Global conflicts conservatively block all snapshot findings because the current
contract has lost finding-level ownership for packet contradictions.
`confidence` does not make an item eligible and is not a business-priority
score. Eligible findings retain canonical input order; the first three are
displayed without “top,” “highest,” or “decision signal” language.

Snapshot eligibility is a renderer-local presentation classification, not a
new review rule. The snapshot displays `Review bundle status` from
`review_summary.status` and never translates `not_required` into the broader
claim “human review is unnecessary.” An unresolved snapshot can therefore
coexist with a `not_required` review bundle without either layer overruling the
other.

Candidate claims never appear in the snapshot in renderer v2, including claims
whose own `verification_status` is `verified`. They remain under `Needs
Verification` or the complete appendix because the contract still names them
candidate claims and P1B durable approval is not enabled. This is intentionally
conservative and can be revisited only with a separately approved contract.

### Empty And Degraded States

| Condition | Required display |
|---|---|
| No findings | `No findings are present in this brief.` |
| Findings exist but none eligible | `No verified evidence-backed findings are available for the snapshot.` |
| No evidence records | Same fail-closed message plus `Evidence records: 0` |
| Missing evidence ref | Item appears only under `Needs Verification`; raw trigger remains in appendix |
| Unverified/conflicting claim | Never appears in snapshot; explicit status in claim block |
| Empty optional section | Omit section unless absence is itself decision-relevant |
| Unknown/malformed summary value | Render `Not declared`; do not infer or coerce truthiness |

### Seven Design Passes

1. **Hierarchy, 9/10 target:** Snapshot, scope, verification needs, boundaries,
   and appendices form a deliberate reading order. Metadata moves to the end so
   implementation identifiers do not displace decision context.
2. **Clarity, 9/10 target:** Use `Evidence-backed findings`, `Candidate claims`,
   `Declared confidence`, `Review bundle status`, and `Snapshot eligibility`.
   Ban “highest-confidence decision signals,” broad claims that human review is
   unnecessary, and ambiguous `None declared` text.
3. **Trust, 10/10 target:** Placement is fail-closed and determined by reference
   resolution, evidence verification, and conflict state. The renderer labels
   its eligibility state separately and cannot override `review_summary` or
   imply approval.
4. **Scanability, 9/10 target:** Only the two-column snapshot may use a Markdown
   table. Long findings, refs, statuses, and limitations render as vertical
   labeled blocks; the snapshot contains at most three findings.
5. **Accessibility, 8/10 target:** Headings and lists preserve a logical reading
   order in plain text and screen readers. Meaning never depends on color, icon,
   hover, or horizontal table scrolling.
6. **Consistency, 9/10 target:** IDs, status terms, and empty-state language are
   deterministic. Similar data uses the same label and ordering throughout.
7. **Validation, 9/10 target:** Byte-exact golden fixtures prove deterministic
   structure while a timed rubric proves that humans can locate the required
   facts. Live model runs remain regression-only evidence.

### Design Acceptance Criteria

- No pending, unverified, conflicting, missing-reference, or review-required
  claim text appears in the snapshot.
- Zero verified evidence produces the explicit empty state and never a fallback
  “top finding.”
- No signal is ranked solely by `confidence`; snapshot findings preserve
  canonical order after eligibility filtering.
- The snapshot contains at most three findings and the only table has two
  columns.
- All findings and claims remain available in complete appendices.
- Untrusted Markdown/HTML characters, table delimiters, backticks, and line
  breaks cannot create executable HTML or new structural rows.
- One fresh independent AI-assisted reviewer completes the five-item rubric in
  120 seconds with 5/5 correct answers before the phase passes. Owner
  confirmation is a brief final delivery check, not a second timed gate.

### Design Dual Voices And Scorecard

Claude's Design CLI was unavailable after three bounded retries: two response-
body decode errors and one aborted long-running stream. The independent Codex
voice and the primary review agreed on both critical blockers and the revised
hierarchy; the phase is therefore recorded as `codex-only`, not falsely marked
as cross-model consensus.

| Dimension | Primary | Independent Codex | Result after revision |
|---|---:|---:|---:|
| Information hierarchy | 5 | 4 | 9 |
| Clarity/terminology | 5 | 4 | 9 |
| Trust semantics | 4 | 3 | 10 |
| Scanability | 4 | 4 | 9 |
| Empty/error states | 3 | 2 | 9 |
| Determinism/safety | 8 | 8 | 9 |
| Validation quality | 4 | 3 | 9 |
| **Overall** | **5** | **5** | **9** |

**Phase 2 result:** The original design is rejected; the bounded snapshot plus
vertical appendices design is selected. No taste decision remains unresolved.

---

## Delivery Boundaries

### In Scope

- Renderer-v2 eligibility helpers and fail-closed empty states.
- Bounded snapshot, scope/coverage, needs-verification, gaps/conflicts,
  limitations, full findings/claims appendices, and artifact metadata.
- `renderer_version="2"`; schema and canonicalization remain `"1"`.
- Byte-exact fixture/golden tests and focused security/state tests.
- A single independent AI-assisted, two-minute readability scorecard with a
  separate answer key.
- Fixed 1x2 then 3x2 regression runbook.
- Runner-level renderer contract validation and a fail-closed completion counter.

### NOT In Scope

| Deferred item | Reason |
|---|---|
| New presentation Pydantic schema | One Markdown consumer does not justify a new public contract |
| JD edits/interview questions/candidate evaluation | Requires new evidence and approval policy |
| UI, ATS, email, spreadsheet, or dashboard adapters | Markdown is the bounded milestone artifact |
| P1B durable HITL | Must pass its separate durability and safety gates |
| Skills, Async Subagents, LLM reviewer | No demonstrated need for this renderer change |
| Re-rendering historical v1 artifacts | Avoid silent mutation of immutable stored outputs |
| Market/adoption claims | Five declared samples and blind review do not establish PMF |
| Persona-specific prioritization | Current contract has no business-priority or persona field |

---

## File-Level Change Range

| Action | File | Purpose |
|---|---|---|
| Modify | `api/decision_brief.py` | Pure renderer-v2 helpers and presentation |
| Modify | `agent/profile_registry.py` | Talent `renderer_version="2"` only |
| Modify | `tests/unit/test_decision_brief.py` | Eligibility, safety, state, and exact golden tests |
| Modify | `tests/unit/test_profile_registry.py` | Version contract |
| Modify | `tests/unit/test_talent_artifacts.py` | Artifact/version/hash regression only |
| Modify | `scripts/talent_value_gate_runner.py` | Validate Talent renderer-v2 artifact contract |
| Modify | `tests/unit/test_talent_value_gate_runner.py` | Corrupt/mismatched artifact fail-closed tests |
| Add | `tests/fixtures/talent-decision-brief-renderer-v2.json` | Representative canonical input |
| Add | `tests/fixtures/talent-decision-brief-renderer-v2.md` | Byte-exact expected Markdown |
| Modify | `benchmarks/talent-hiring-signal-v1/README.md` | Deterministic, independent readability, and live regression procedure |
| Add | `benchmarks/talent-hiring-signal-v1/renderer-v2-readability-scorecard.md` | Timed AI-assisted independent gate |
| Add | `benchmarks/talent-hiring-signal-v1/renderer-v2-readability-answer-key.md` | Separate post-timer scoring key |
| Modify | Source spec | Align terminology, hierarchy, and validation with this review |

`api/talent_artifacts.py`, contracts, review service, database, API routes,
prompts, and model code should remain unchanged. If implementation proves a
runtime change outside this table is necessary, stop and amend the plan first.

---

## Implementation Tasks

### Task 1: Lock Renderer Contract With RED Tests

- [ ] Add the representative JSON fixture containing eligible findings,
  missing-reference findings, unverified/conflicting candidate claims, evidence
  gaps, long text, Markdown delimiters, and HTML-like input.
- [ ] Add the expected renderer-v2 Markdown golden file.
- [ ] Add a byte-exact test: validated fixture -> `with_content_hash()` ->
  `render_markdown()` equals golden bytes.
- [ ] Add focused RED tests proving:
  - zero evidence yields no snapshot finding;
  - missing/unverified evidence excludes a finding from the snapshot;
  - candidate claims never appear in the snapshot;
  - canonical order is preserved and the snapshot is capped at three;
  - all findings/claims still appear in appendices;
  - escaping prevents HTML and Markdown structural injection;
  - unknown optional summary values display `Not declared` without exceptions.
- [ ] Add parameterized malformed-state tests covering non-dict evidence items,
  unhashable/empty IDs, invalid status values, duplicate IDs, mixed verified and
  unverified refs, empty refs created through `model_construct`, non-bool review
  flags, and invalid quality-summary values.
- [ ] Add the profile test proving only `renderer_version` changes to `2`.

Run and record RED:

```bash
python -m pytest \
  tests/unit/test_decision_brief.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_talent_artifacts.py -q
```

Expected: new renderer and version assertions fail for the intended reasons;
existing tests remain green.

### Task 2: Implement Pure Renderer-v2 Helpers

- [ ] Add defensive evidence indexing over `brief.evidence_summary`. Accept only
  non-empty string IDs with a known verification status; mark every duplicate
  ID ambiguous and exclude it from the verified index.
- [ ] Add `_is_snapshot_eligible(finding, evidence_by_id)` using the approved
  non-empty-reference, evidence-resolution, finding-conflict, and global-conflict
  criteria.
- [ ] Derive snapshot counts from typed collections, not `quality_summary`.
- [ ] Read review flags without `bool(value)` coercion; malformed values render
  `Not declared`.
- [ ] Keep the snapshot table limited to fixed labels and controlled scalar
  values. Normalize CR/LF and U+2028/U+2029, remove non-printing control
  characters, HTML-escape `<>&"`, and escape Markdown structural characters in
  every untrusted prose context. Do not generate links or images from untrusted
  URLs.
- [ ] Render the required hierarchy with vertical labeled blocks for long data.
- [ ] Use explicit empty-state copy from Phase 2.
- [ ] Preserve every canonical finding and claim in appendices.
- [ ] Change only `TALENT_PROFILE.renderer_version` to `"2"`.
- [ ] Keep `executive_summary` count-only and human-readable; do not add ranked
  claims or findings to canonical JSON.

Run GREEN:

```bash
python -m pytest \
  tests/unit/test_decision_brief.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_talent_artifacts.py -q
```

### Task 3: Verify Persistence And Retrieval Compatibility

- [ ] Prove artifact IDs and media types remain `decision-brief.json` and
  `decision-brief.md`.
- [ ] Prove renderer version changes the canonical semantic hash while changing
  only `generated_at` does not, even though rendered bytes include timestamp.
- [ ] Prove retrieved artifacts contain the same bytes that were finalized.
- [ ] Document that stored renderer-v1 artifacts are immutable and not migrated.
- [ ] Document that existing `content_hash` is a canonical semantic hash shared
  by JSON and Markdown, not an artifact-byte checksum. Do not change the field
  contract in this phase.

Run:

```bash
python -m pytest \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py -q
```

### Task 4: Document And Execute Readability Gates

- [ ] Update the source spec to remove confidence-only ranking, wide tables,
  zero-evidence fallback, and “decision signal” wording.
- [ ] Update the benchmark README with three distinct gates:
  1. byte-exact deterministic renderer tests;
  2. timed AI-assisted independent readability scorecard;
  3. 1x2 then 3x2 live regression.
- [ ] Add the scorecard with five questions:
  1. What scope does this brief cover?
  2. What is the review bundle status and what is the separate snapshot
     eligibility state?
  3. Which findings are evidence-backed in the snapshot?
  4. Which candidate claim still needs verification and why?
  5. What is the most important gap, conflict, or limitation?
- [ ] Require one fresh, read-only AI session to answer all five correctly
  within 120 seconds without opening JSON, implementation code, or the separate
  answer key.
- [ ] Record elapsed time, answers, score, and pass/fail using
  `ai-assisted-independent-reviewer`. Do not describe it as human review.
- [ ] Keep owner confirmation as a brief final delivery check, not a second
  timed benchmark gate.

### Task 5: Make The Live Renderer Contract Fail Closed

- [ ] Add deterministic Talent artifact validation inside
  `build_benchmark_bundle()` before export sanitization.
- [ ] Require exactly one JSON and one Markdown artifact with the expected ID,
  kind, media type, non-empty content, and matching declared semantic hash.
- [ ] Parse JSON as `DecisionBrief`, require `renderer_version="2"`, recompute
  the canonical semantic hash, and require Markdown content to equal
  `render_markdown(parsed_brief)` byte-for-byte before sanitization.
- [ ] Add `renderer_contract_failure_count` and require zero for
  `completion.ready_for_human_review=true`.
- [ ] Test missing, duplicate, malformed, wrong-version, wrong-hash, empty, and
  mismatched Markdown artifacts. The counter is independent, so one bad run may
  increment more than one diagnostic counter.
- [ ] Keep writing the diagnostic bundle on failure, print its output path, and
  make CLI `main()` exit nonzero whenever `benchmark_status !=
  "ready_for_human_review"`. Add a CLI test for ready `0` and incomplete `1`.

### Task 6: Full And Live Regression

Run focused and full checks:

```bash
python -m pytest \
  tests/unit/test_decision_brief.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_talent_value_gate_runner.py \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py -q
python -m pytest -q
python -m compileall -q api/decision_brief.py
git diff --check
```

Load the primary checkout `.env` without printing values, run 1x2, and stop on
any failure:

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

Required 1x2 result: two completed runs,
`completion.ready_for_human_review=true`, zero readiness failure counters,
Talent JSON has `renderer_version="2"`, and Talent Markdown satisfies the
renderer-v2 section contract. `renderer_contract_failure_count` must be `0`.

Only then run 3x2:

```bash
python -m dotenv -f "$ENV_FILE" run -- python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-3x2.json
```

Required 3x2 result: six completed runs,
`completion.ready_for_human_review=true`, all readiness failure counters remain
zero, and all three Talent Markdown artifacts satisfy the section and trust
contract. This proves end-to-end stability, not readability or wider market
value.

### Task 7: Pre-Landing Review And Handoff

- [ ] Run a light `gstack-review` over the complete branch diff, focused on
  injection, fail-open eligibility, deterministic bytes, hash/version semantics,
  appendices, artifact compatibility, and exact scope.
- [ ] Use `superpowers:verification-before-completion` with fresh output.
- [ ] Report branch/worktree, commits, actual test counts, AI-assisted
  scorecard results, 1x2/3x2 counters, compatibility, rollback, and deferred
  work.
- [ ] Do not push or create a PR until explicitly approved.

---

## Architecture Diagram

```text
ResearchPacket + EvidenceLedger snapshots
                 |
                 v
       build_talent_artifacts()
       - existing review authority
       - existing DecisionBrief schema
                 |
                 v
          DecisionBrief JSON
                 |
                 v
       render_markdown() v2
       +-----------------------------+
       | evidence index (defensive)  |
       | snapshot eligibility filter |
       | bounded reading layer       |
       | complete appendices         |
       | context-aware escaping      |
       +-----------------------------+
                 |
                 v
       immutable decision-brief.md

Authority direction:
EvidenceLedger/review state -> renderer
renderer -X-> evidence or review state mutation
renderer -X-> model calls, filesystem tools, advice generation
```

## Test Diagram

| Codepath/branch | Test type | Required coverage |
|---|---|---|
| Renderer version bump | Unit | schema/canonicalization unchanged; hash changes |
| Fully verified, non-empty refs | Unit + golden | finding eligible in snapshot |
| Missing ref | Unit + golden | excluded from snapshot; present in verification/detail |
| Unverified evidence | Unit + golden | excluded from snapshot |
| Duplicate evidence IDs | Unit | all duplicates ambiguous and fail closed |
| Empty refs through `model_construct` | Unit | never eligible; no `all([])` bug |
| Contradiction | Unit + golden | excluded from snapshot; conflict visible |
| Global brief conflict | Unit + golden | all snapshot findings blocked |
| Candidate claim, any status | Unit + golden | never in snapshot; preserved in appendix |
| Zero evidence | Unit | explicit fail-closed empty state |
| More than three eligible findings | Unit | snapshot capped; appendix complete |
| Long/hostile text | Security unit | no HTML/Markdown structural injection |
| Empty optional fields | Unit | specific state or omitted section; no crash |
| Malformed dict values | Parameterized unit | no exception, no truthy coercion, `Not declared` |
| Golden bytes | Snapshot unit | exact UTF-8 equality |
| Finalized artifact retrieval | Integration | IDs/media types/content preserved |
| Independent comprehension | Timed AI-assisted review | one fresh read-only session, 5/5 within 120 seconds |
| Live service path | 1x2 then 3x2 | completion/readiness and artifact contract |
| Corrupt live artifact | Runner unit | renderer counter increments and ready=false |
| Large canonical brief | Unit | complete appendices and linear implementation path |

## Error And Rescue Registry

| Failure | Detection | Rescue | Stop condition |
|---|---|---|---|
| Golden mismatch | Exact pytest diff | Inspect intentional contract change; update fixture only with review | Never auto-accept fixture rewrite |
| Malformed evidence summary | Unit and defensive parser | Treat as unresolved; render under verification/detail | Do not display in snapshot |
| Duplicate evidence identity | Unit | Mark ID ambiguous and exclude every duplicate | Never last-write-wins |
| No eligible findings | Empty-state test | Render explicit no-verified-findings message | Do not fallback by confidence |
| HTML/Markdown injection | Security assertions | Escape by context; keep plain-text structure | Any raw executable tag blocks merge |
| 1x2 failure | Completion counters | Stop; use systematic debugging | Never continue to 3x2 |
| Human rubric failure | Scorecard | Revise hierarchy/copy and repeat with fresh reviewer | Do not claim readability pass |
| Missing `.env` | `test -f` | Report external configuration blocker | Do not print or copy secrets |
| Claude review unavailable | Three bounded failures | Record `codex-only`; continue with independent Codex | Do not claim cross-model consensus |

## Failure Modes Registry

| Failure mode | Severity | Prevention/coverage | Residual risk |
|---|---|---|---|
| Unverified claim promoted to decision signal | Critical | Claims banned from snapshot; golden state coverage | Low |
| Missing evidence treated as verified | Critical | All refs must resolve and be verified | Low |
| Confidence interpreted as business priority | High | No confidence-only ranking or “top” language | Medium; readers still see declared confidence in appendix |
| Wide tables become unreadable | High | Only 2-column snapshot table; vertical detail blocks | Low |
| Detail lost by snapshot cap | High | Complete appendices and cap test | Low |
| Renderer change without version bump | High | Profile contract and hash tests | Low |
| Old artifacts silently change | High | No rerender/migration; document immutability | Low |
| Hostile content changes Markdown structure | High | Context-aware escaping tests | Low |
| Live benchmark noise mistaken for UX evidence | Medium | Separate deterministic/human/live gates | Low |
| Renderer accumulates business rules | Medium | Eligibility limited to existing states; no new authority | Medium; revisit with second consumer |
| Unbounded appendices consume resources | Medium | Single evidence index and linear rendering; scale test | Accepted until a separately approved input-limit contract |
| Runner reports ready for corrupt renderer | High | `renderer_contract_failure_count` | Low |
| Incomplete CLI run chains into 3x2 | High | Nonzero exit after writing diagnostics | Low |

---

## Phase 3: Engineering Review

### Scope And Existing-Code Assessment

The selected ownership boundary remains sound: canonical data is built in
`api/talent_artifacts.py`, review authority stays in `api/review_service.py`, and
presentation stays in `api/decision_brief.py`. The review rejected expanding
review-service triggers merely to make renderer labels convenient; instead the
plan now distinguishes server review status from renderer-local snapshot
eligibility. This avoids a behavior change to delivery status while preserving
fail-closed presentation.

The only justified expansion is benchmark tooling. The current runner considers
artifact IDs sufficient, so a corrupt or v1 renderer can still produce
`ready_for_human_review=true`. Adding a deterministic renderer contract counter
closes that acceptance gap without changing the service API or research
contract.

### Architecture Assessment

The renderer must construct one evidence index and then traverse findings,
claims, and refs once. Target complexity is `O(E + F + C + R)` and memory is
`O(E + output)`. Any implementation that scans all evidence for each finding is
rejected.

Complete appendices remain intentionally untruncated because silent truncation
would violate the canonical audit purpose. Since `ResearchPacket` list lengths
are not schema-bounded, availability risk remains. A scale test guards against
accidental superlinear work; hard limits require a separate contract decision.

### Code Quality

Use small pure helpers with names that encode trust semantics:
`_build_evidence_index`, `_snapshot_eligible_findings`, `_plain_text`, and
`_render_*_section`. Do not mix review-rule generation into these helpers.
Avoid one generic escaping helper used in incompatible contexts; the two-column
snapshot contains controlled scalars, while untrusted prose uses a dedicated
normalization/escaping path.

The runner validator should return a boolean or compact failure code set and
must not throw on malformed benchmark artifacts. It reuses
`DecisionBrief.model_validate_json`, `with_content_hash`, and `render_markdown`
rather than duplicating canonicalization or renderer logic.

### Performance

No network, database, or model call is added to artifact creation. Rendering is
linear and runs once per Talent finalization. The live 3x2 run remains the
dominant cost, so deterministic and independent readability gates run before it and any 1x2
failure stops further model spend.

The scale test is correctness-oriented, not a brittle wall-clock benchmark. It
uses a representative large brief and verifies complete output plus the absence
of nested evidence scans through implementation review. Performance thresholds
can be added later only if real artifact sizes justify them.

### Security

All model/source text is untrusted. The renderer never emits raw HTML, links, or
images from that text, removes control characters that can alter display,
normalizes line separators, and escapes Markdown structure. Golden tests alone
are insufficient; focused adversarial tests cover headings, lists, blockquotes,
links, images, HTML, pipes, backticks, CRLF, NUL, and bidi/control characters.

No secrets are read by renderer tests. Live benchmark commands load `.env`
through `python-dotenv` without printing values and write outputs only under
`/tmp`. The public AI-assisted scorecard records reviewer roles, not identities.

### Deployment And Rollback

Renderer code and `TALENT_PROFILE.renderer_version="2"` must ship in the same
commit/atomic deployment. A rollback reverts both; changing only the constant is
not valid. Existing v1 or v2 artifacts remain immutable and are not migrated or
rerendered.

There is no database migration. Artifact bytes and canonical semantic hashes
for new Talent runs change, so caches or snapshots keyed by those values must
not assume cross-version equality. Generate the fixed fixture before and after
deployment and verify version, semantic hash, and golden Markdown.

### Engineering Dual Voices

The primary review and independent Codex agreed on malformed-state coverage,
runner contract validation, hash terminology, precise escaping, linear
rendering, and atomic rollback. They initially differed on changing review
authority; the plan selected the smaller explicit-status approach because it
preserves the approved service boundary. Claude remained unavailable for this
phase, so cross-model consensus is not claimed.

| Dimension | Claude | Independent Codex | Revised result |
|---|---|---:|---:|
| Architecture sound | N/A | 5 | 9 |
| Test coverage sufficient | N/A | 4 | 9 |
| Performance addressed | N/A | 4 | 8 |
| Security covered | N/A | 5 | 9 |
| Error paths handled | N/A | 3 | 9 |
| Deployment manageable | N/A | 4 | 9 |

### Engineering Completion Summary

| Area | Initial gap | Resolution | Status |
|---|---|---|---|
| Authority | Eligibility could contradict review wording | Separate review status from snapshot state | Closed |
| Malformed data | Open dictionaries could fail open or crash | Strict defensive parsing and duplicate rejection | Closed in plan |
| Live gate | IDs only | Renderer contract counter | Closed in plan |
| Hash | Confused with byte checksum | Canonical semantic hash terminology | Closed |
| Escaping | Generic and underspecified | Context-specific normalization and adversarial cases | Closed in plan |
| Scale | Appendices unbounded | Linear implementation plus scale test; risk accepted | Deferred hard limit |
| Rollback | Version-only rollback ambiguous | Atomic code/version rollback | Closed |

**Phase 3 result:** `REVISE BEFORE IMPLEMENTATION` findings are incorporated.
No critical engineering gap remains in the revised plan; the accepted residual
risk is unbounded canonical list size pending a separate schema/input-limit
decision.

## Phase 3.5: Developer Experience Review

### Scope And Persona

This phase reviews the repository-local renderer implementer and benchmark
operator, not general product onboarding. The primary persona already has the
project environment or can follow the repository setup and wants the cheapest
credible proof before spending model time. Initial DX was 3.9/10 because the
current README sends that person directly to 3x2 and the v2 fixtures do not yet
exist.

The target is a deterministic proof in at most two minutes in a warm
environment and at most five minutes from a prepared clean checkout, excluding
first dependency download. Live-model TTHW is reported separately because it
is intentionally slower and credential-dependent.

### Nine-Stage Developer Journey

| Stage | Required experience |
|---|---|
| 1. Find entry | Benchmark README begins with renderer-v2 purpose, three gates, order, and expected duration |
| 2. Preflight | Copy-paste checks for Python 3.11+, dependencies, writable temp dir, `.env`, and required variable presence without values |
| 3. Deterministic proof | One focused pytest command validates v2 and golden bytes without model credentials |
| 4. Inspect change | Fixture/golden paths and “never auto-update” rule are explicit |
| 5. Readability gate | Scorecard names artifact, timing start/stop, separate answer key, AI-assisted role, threshold, and retry record |
| 6. 1x2 smoke | Separate command and exact success counters; nonzero exit on incomplete |
| 7. Diagnose | Output path survives failure; README maps common counter/error to cause and next action |
| 8. 3x2 regression | Separate command, allowed only after earlier gates pass |
| 9. Upgrade/rollback | v1/v2 difference, semantic hash effect, immutable history, and whole-change rollback are explicit |

### Developer Empathy Narrative

> I want to prove that the renderer itself is deterministic and trustworthy
> before I spend time or API budget on six model runs. I should not have to
> infer which `.env` to load, whether a zero exit means the benchmark passed, or
> which artifact contract was actually validated. When a gate fails, I need the
> output path, the failing counter, and a concrete next action while preserving
> the diagnostic bundle.

### Operator-First README Structure

```text
1. Renderer v2 purpose and evidence boundary
2. Gate order and expected durations
3. Environment preflight (no secret values printed)
4. Deterministic golden command
5. Timed AI-assisted scorecard command/procedure
6. 1x2 command and exact counters
7. Troubleshooting table
8. 3x2 command and exact counters
9. Upgrade and rollback
10. Advanced service fixture boundary
11. Benchmark limitations
```

The preflight must check `python --version`, importability of required project
modules, a writable temporary directory, presence of the selected `.env`, and
presence (not value) of required model variables inside the dotenv subprocess.
It must not print keys or copy `.env` into a worktree.

### Error And Action Guidance

| Signal | Meaning | Next action |
|---|---|---|
| Golden mismatch | Renderer contract bytes changed | Inspect diff; update golden only after approved contract change |
| Temp directory error | Python/pytest cannot create temp files | Set a verified writable `TMPDIR` and rerun deterministic gate |
| Missing `.env`/model variable | Live gate cannot initialize model | Select primary checkout `.env`; verify names only |
| `runner_timeout` | One profile exceeded per-run limit | Inspect recorded profile/repetition; diagnose before retry |
| `renderer_contract_failure_count` | Artifact is missing, malformed, v1, hash-invalid, or Markdown-mismatched | Inspect Talent artifacts; do not run 3x2 |
| Other readiness counter | Research/profile/evidence contract failed | Follow existing counter definition and inspect failed run |
| Human score below 5/5 | Hierarchy is not reliably scannable | Revise renderer/copy and use a fresh independent review |

### DX Implementation Checklist

- [ ] README first screen states scope, three gates, order, and duration.
- [ ] Deterministic gate is explicitly credential-free and copy-paste complete.
- [ ] Preflight checks version/dependencies/temp/env without exposing values.
- [ ] Golden fixture and scorecard paths are directly linked.
- [ ] Scorecard defines artifact, separate answer key, timer protocol,
  AI-assisted role, threshold, and failed-attempt history.
- [ ] 1x2 and 3x2 use different `/tmp` output names.
- [ ] Runner writes diagnostics, prints output path, and exits `1` on incomplete.
- [ ] README requires 1x2 success before 3x2.
- [ ] Troubleshooting states problem, likely cause, and next action.
- [ ] README documents v1 immutability, v2 semantic-hash/byte change, and whole-
  commit rollback.
- [ ] Advanced service fixture details no longer interrupt the primary offline
  operator flow.

### TTHW

| Milestone | Current | Target |
|---|---:|---:|
| Warm deterministic proof | Unavailable | <=2 minutes |
| Prepared clean-checkout proof | Unavailable | <=5 minutes, excluding dependency download |
| Independent readability gate | Template unavailable | <=120 seconds |
| 1x2 live regression | Undocumented direct path | <=10 minutes normal; 20-minute timeout ceiling |
| 3x2 live regression | README starts here; up to 60-minute ceiling | <=30 minutes normal; 60-minute ceiling |

### Eight-Dimension DX Scorecard

| Dimension | Current | Target after plan |
|---|---:|---:|
| Time to first deterministic proof | 2 | 9 |
| Copy-paste command quality | 5 | 9 |
| Environment handling | 3 | 8 |
| Runner diagnostics | 5 | 9 |
| Documentation findability | 4 | 9 |
| v1 -> v2 upgrade/rollback | 5 | 9 |
| Progressive disclosure | 3 | 9 |
| Error/action guidance | 4 | 9 |
| **Overall** | **3.9** | **8.9** |

### DX Dual Voices

The primary and independent Codex voices agreed that the current implementation
and README are still the v1 baseline and that the revised plan must deliver an
operator-first deterministic path, actionable failure semantics, and a
discoverable rollback. Claude was unavailable after the earlier bounded retry
threshold, so this phase is also recorded `codex-only`.

| Dimension | Claude | Independent Codex | Revised plan |
|---|---|---:|---:|
| Getting started under five minutes | N/A | 2 | 9 |
| CLI naming/behavior guessable | N/A | 5 | 9 |
| Errors actionable | N/A | 4 | 9 |
| Docs findable/complete | N/A | 4 | 9 |
| Upgrade path safe | N/A | 5 | 9 |
| Environment friction controlled | N/A | 3 | 8 |

**Phase 3.5 result:** DX gaps are converted into implementation requirements.
The plan does not claim current tests passed; the independent sandbox could run
runner `--help` in 0.17 seconds but could not start pytest because that isolated
environment had no writable temporary directory.

---

## Cross-Phase Themes

1. **Trust semantics:** CEO, Design, Engineering, and DX all rejected using
   confidence or artifact existence as a proxy for verified usefulness.
2. **Deterministic proof before model spend:** CEO, Engineering, and DX require
   golden and contract checks before 1x2/3x2.
3. **Progressive disclosure:** Design and DX require bounded first-read content
   while retaining complete evidence appendices and advanced operator details.
4. **Explicit compatibility:** CEO, Engineering, and DX require renderer-v2
   versioning, semantic-hash wording, immutable historical artifacts, and atomic
   rollback.

## Final Stage Acceptance

The implementation phase passes only when all of the following are true:

- focused, integration, full, compile, and diff checks pass with fresh output;
- golden bytes and all malformed/hostile-state tests pass;
- the timed AI-assisted independent reviewer scores 5/5 within 120 seconds;
- 1x2 is 2/2 ready with every readiness counter, including renderer contract,
  at zero;
- 3x2 is 6/6 ready with the same zero-counter contract;
- docs contain executable preflight, troubleshooting, upgrade, and rollback;
- light pre-landing review finds no unresolved critical/high issue.

---

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---:|---|---|---|---|---|---|
| 1 | CEO | Keep the P1A.1 readability milestone | User-confirmed | Bias to action | Known blind-review weakness; bounded correction | Reframe as PMF/adoption study |
| 2 | CEO | Keep schema/model/API scope unchanged | Auto-decided | Simplicity | Existing contract already contains required display data | New presentation schema now |
| 3 | CEO | Treat Markdown as audit artifact only | User-confirmed | Explicit boundaries | Avoid implying final product channel | ATS/UI expansion |
| 4 | Design | Ban candidate claims from snapshot | Auto-decided | Trust over cleverness | Contract still identifies them as candidate claims | Confidence-ranked claims |
| 5 | Design | Require verified, resolved evidence refs for snapshot findings | Auto-decided | Completeness | Prevent fail-open presentation | Declared-ref-only eligibility |
| 6 | Design | Preserve canonical order after filtering | Auto-decided | Explicit over clever | Contract has no business-priority field | Confidence-only ranking |
| 7 | Design | Cap snapshot at three and preserve full appendices | Auto-decided | Progressive disclosure | Fast scan without data loss | Unbounded overview tables |
| 8 | Design | Use vertical blocks for long content | Auto-decided | Accessibility | Avoid horizontal overflow and dense 7-column tables | Wide Markdown matrices |
| 9 | Design | Add golden and timed independent readability gates | User-confirmed, amended 2026-06-19 | Verify the actual outcome without unnecessary manual process | Existing live benchmark cannot prove readability | Two required human reviewers or substring tests only |
| 10 | Design | Keep `executive_summary` count-only | Auto-decided | Minimal compatibility change | Avoid promotion and parsing assumptions | Ranked summary text |
| 11 | Design | No migration for stored renderer-v1 artifacts | Auto-decided | Immutability | Historical artifacts must not change silently | Bulk rerender |
| 12 | Design | Record Claude Design voice as unavailable | Auto-decided | Evidence honesty | Three bounded CLI attempts produced no review | Fabricated consensus |
| 13 | Eng | Keep renderer eligibility separate from review authority | Auto-decided | Scope control | Avoid changing delivery behavior in a readability PR | Add new review triggers |
| 14 | Eng | Global conflicts block every snapshot finding | Auto-decided | Fail closed | Packet conflict ownership is unavailable | Ignore global conflicts |
| 15 | Eng | Reject duplicate evidence IDs | Auto-decided | Explicit over clever | Prevent last-write-wins verification | Keep final duplicate |
| 16 | Eng | Derive counts from typed collections | Auto-decided | Trust boundary | Open quality dictionary is not authoritative | Coerce arbitrary values |
| 17 | Eng | Add runner renderer-contract counter | Auto-decided | Complete verification | Live readiness must validate actual artifact contract | Manual-only inspection |
| 18 | Eng | Keep existing hash field semantics | Auto-decided | Compatibility | Rename it in docs, not storage/API | Add byte hashes now |
| 19 | Eng | Require linear rendering and accept current list-size risk | Auto-decided | Pragmatism | Hard caps are a separate schema decision | Silent appendix truncation |
| 20 | Eng | Atomically deploy and rollback renderer plus version | Auto-decided | Operational safety | Version and implementation form one contract | Constant-only rollback |
| 21 | DX | Put deterministic proof before live benchmark | Auto-decided | Progressive disclosure | Cheapest credible feedback should come first | README starts with 3x2 |
| 22 | DX | Exit nonzero on incomplete runner result | Auto-decided | Actionable automation | Shell/CI must distinguish diagnostic output from success | Always exit 0 |
| 23 | DX | Keep diagnostic bundle on failed exit | Auto-decided | Recoverability | Operators need evidence after failure | Abort before write |
| 24 | DX | Document writable-temp rescue and env-name preflight | Auto-decided | Completeness | Real isolated review exposed this failure mode | Generic “valid config” text |
| 25 | DX | Use role labels in public scorecard | Auto-decided | Privacy | Identity adds no verification value | Personal reviewer names |
| 26 | DX | Move service fixture details to advanced docs | Auto-decided | Findability | Preserve detail without interrupting primary path | Delete service guidance |
