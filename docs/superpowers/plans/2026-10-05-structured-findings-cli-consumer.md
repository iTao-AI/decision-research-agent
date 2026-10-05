# Structured findings CLI and consumer implementation plan

> **For agentic workers:** Implement serially in the current owner context with
> `superpowers:test-driven-development` and completion verification, followed by
> one fresh whole-branch review. The approved execution route is direct; do not
> add per-task implementation/review agents or parallel execution logs.

**Goal:** Read an existing structured run through the Tool Client and consume
it independently without moving delivery or verification authority.

**Architecture:** Add a bounded GET-only findings path to the existing CLI.
A separate stdlib consumer launches that CLI and validates the public delivery
package before writing a small receipt. Existing server readers remain unchanged.

**Tech Stack:** Locked Python 3.11 environment, stdlib urllib/subprocess/JSON,
existing FastAPI service and installed native fixture, pytest.

**Spec:** [Read-only structured findings CLI and consumer](../specs/2026-10-05-structured-findings-cli-consumer.md)

## Global constraints

- Base: `243a1e935e5ec138b0c68a755345582f69d28940`; isolated `codex/findings-cli-consumer`.
- Profile/schema: `generic-evidence-report@1`, `dra.research-findings.v1`.
- Artifact content at most 1 MiB; HTTP at most `4 * 1024 * 1024 + 65536` bytes;
  error at most 65536 bytes; receipt at most 256 KiB.
- Timeout `0 < timeout <= 60`, finite; consumer deadline `4 * timeout + 10`.
- No new dependency/lock changes, provider calls, server contracts or authority changes.
- Local commits authorized; hosted delivery requires separate authorization.

## Review focus

- Bad endpoint, NaN/infinite timeout or header configuration must fail before HTTP.
- Invalid UTF-8, duplicate/nonfinite JSON, huge or trickled replies must remain bounded.
- Markdown must retain exact canonical bytes and reject legacy-profile fallback.
- Partial/unresolved and approved/unverified states must survive consumption.
- Existing output files and child failures must not acquire a success receipt.

## Task 1: Read-only Tool Client command

**Files:** Modify `tools/decision_research_agent_tool.py`; create
`tests/unit/test_research_findings_tool.py`.

**Interfaces:** Add `findings(run_id, config, *, output_format='json') -> dict | str`;
add strict findings-only configuration, bounded GET parsing and UTF-8 emission.
Existing command functions/signatures/transport behavior remain intact.

- [x] Write regressions for exact JSON plus public verification, Markdown bytes,
  only-GET order, service errors, malformed replies/configuration and size bounds.
- [x] Run `python -m pytest -q tests/unit/test_research_findings_tool.py` and
  observe absent-command/implementation failures.
- [x] Implement the interfaces and parser dispatch with only the spec's new path.
- [x] Run the new tests plus `tests/unit/test_decision_research_agent_tool.py`;
  require all passing and `git diff --check` clean.
- [x] Commit the CLI, tests and approved public spec/plan with explicit staging.

## Task 2: Independent consumer and actual process/HTTP proof

**Files:** Create `scripts/research_findings_consumer.py`,
`tests/unit/test_research_findings_consumer.py`,
`tests/integration/test_research_findings_consumer_journey.py`.

**Interfaces:** Consumer `main(argv=None) -> int` invokes Task 1's JSON CLI;
`validate_delivery(package, run_id) -> dict` returns the bounded receipt.
Use existing `scripts/research_evidence_delivery_proof.py serve` and declared
`tests/fixtures/research-evidence-delivery/{cases,expected}.json` unchanged.

- [ ] Write consumer rejection tests for cross-run, offset, URL, coverage,
  rehashed content, false verification, child failure/timeout and existing output.
- [ ] Write actual server-process / CLI-process / consumer-process journey tests:
  complete ready with unverified references; partial 2/1 unresolved;
  contradictory 2 references/1 reported contradiction; insufficient blocked,
  no receipt; Markdown equals direct HTTP's canonical content bytes.
- [ ] Add controlled negative-only server fixtures for pending/wrong-profile,
  approval plus unverified, tampering and actual slow/invalid UTF-8 HTTP.
- [ ] Observe failures before implementing the stdlib-only consumer.
- [ ] Implement independent validation and exclusive bounded receipt creation.
- [ ] Run all new regressions and existing findings/native/generic consumer tests;
  require green and clean diff; commit intentional implementation and tests.

## Task 3: Documentation and integrated acceptance

**Files:** Create `docs/reference/research-findings-cli.md`; modify
`docs/operations/research-evidence-delivery.md`, `docs/AGENT_INTEGRATION.md`,
`README.md` and this implementation record's completion checkboxes.

**Interfaces:** Document the exact flags, response/error/receipt boundaries and
reproducible native-server commands defined in the spec.

- [ ] Write usage documentation, including observed verification location,
  strict findings-only configuration, UTF-8 stdout and consumer producer limits.
- [ ] Run `python -m pytest -q -m 'not docker'` and dependency compatibility;
  retain local logs in ignored output, not public documents.
- [ ] Run a separate manual bounded native-server/consumer command and inspect
  the actual receipt and canonical Markdown bytes; terminate owned resources.
- [ ] Run `git diff --check`, inspect the full intended diff and legacy-file
  preservation; commit documents and completed task checkboxes.
- [ ] Dispatch one bounded fresh `gpt-6.1-sol/high` whole-branch reviewer, resolve
  actionable findings with regressions and rerun affected/full checks as needed.
- [ ] Return exact HEAD, branch/worktree, actual checks, consumer/producer proof
  boundaries and remaining hosted authorization once. Keep the local branch.

## Plan review

The delivery owner checked spec coverage, interface names, task dependencies,
test inputs and scope. Tasks are serial because transport/output/receipt
contracts are coupled. The CLI confirms accepted questions against public scope;
the independent consumer rechecks delivered structure and source binding.
No backend API/schema change or ADR change is needed because authority remains
in the existing persisted readers.
