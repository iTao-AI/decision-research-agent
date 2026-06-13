# Fair Talent Value Gate Design

## Goal

Provide a repeatable, offline benchmark runner that compares the existing
`generic` and `talent-hiring-signal` profiles with the same bounded source
snapshot, without expanding either profile's production permissions.

The runner collects review-ready evidence. It does not automatically claim that
the Talent profile passes the P1A value gate.

## Experiment Boundary

The comparison must isolate profile behavior from source accessibility:

- Both profiles receive the same immutable prompt envelope containing the five
  bundled source snapshots.
- Both profiles receive the same research questions and explicit instruction not
  to use sources outside the envelope.
- The Talent run additionally receives the validated `ResearchScope`, because
  scope enforcement and the structured `ResearchPacket` contract are the
  behavior under evaluation.
- The runner invokes `run_deep_agent()` directly. It does not use legacy
  `/api/task`, change API contracts, or grant `generic` access to
  `provided_aggregate`.
- The bundled fixture remains disabled for normal service execution.

This design measures the profiles' ability to produce bounded, reviewable
research from equivalent inputs. It does not measure live-search quality.

## Architecture

`scripts/talent_value_gate_runner.py` owns orchestration and result export:

1. Load and validate the declared scope and bundled fixture.
2. Build one deterministic prompt envelope from the fixture.
3. Run `generic` and `talent-hiring-signal` sequentially for each repetition.
4. Capture each `AgentRunResult`, elapsed time, evidence, diagnostics, structured
   packets, and failure state.
5. Build Talent artifacts using the existing deterministic artifact service when
   the Talent run returns a valid packet.
6. Write a single JSON review bundle with `benchmark_status=incomplete` until all
   expected runs completed successfully.

The runner keeps human scoring separate from runtime collection. Reviewers score
the four existing dimensions: evidence coverage, scope adherence, limitations,
and reviewability.

## Data Contract

The exported JSON contains:

- `benchmark_id`, fixture hash, scope hash, generated timestamp, repetition
  count, and model configuration names.
- One paired result per repetition with distinct `run_id` and shared input hash.
- For each run: profile, status, failure kind, elapsed time, final text,
  diagnostics, evidence snapshots, research packets, and Talent artifact
  metadata/content when available.
- `completion`: expected run count, completed run count, schema failure count,
  out-of-scope evidence count, and whether the bundle is ready for human review.
- An empty human-scoring section that cannot report `passed=true` until a human
  supplies all four paired scores.

No secret values, filesystem paths, API keys, or LangSmith payloads are written
to the result.

## Validation And Failure Handling

- Fixture and scope IDs must match and every fixture sample must have a declared
  HTTP(S) source URL and non-empty content.
- The prompt envelope is byte-stable for the same fixture and scope.
- Every run gets a unique `thread_id`, `run_id`, and `segment_id`.
- Exceptions become failed run records; earlier paired results remain in the
  bundle.
- Missing Talent `ResearchPacket` is a schema failure and keeps the benchmark
  incomplete.
- Evidence URLs outside the fixture's declared URL set are counted by Profile
  for the human scope-adherence score. They do not make a completed comparison
  incomplete, because the violation is itself a benchmark result.
- A partial or failed run never produces a passing value-gate claim.

## Files

- Create `scripts/talent_value_gate_runner.py`: offline paired-run orchestration
  and deterministic JSON export.
- Create `tests/unit/test_talent_value_gate_runner.py`: input, serialization,
  scope, failure, and completion tests.
- Update `benchmarks/talent-hiring-signal-v1/README.md`: exact execution and human
  review procedure.

No service API, profile policy, persistence schema, or production tool changes
are in scope.

## Acceptance Criteria

1. The runner proves both profiles receive the same input envelope hash.
2. A mocked paired execution produces a deterministic, review-ready result
   bundle without secrets or filesystem paths.
3. Failed or schema-invalid runs produce `benchmark_status=incomplete`;
   out-of-scope evidence remains visible for human scoring.
4. The runner cannot emit `value_gate.passed=true`.
5. Unit tests and the full backend suite pass.
6. A real benchmark run is attempted only when explicitly configured with valid
   model credentials; its result is reported as evidence, not silently treated
   as a product claim.
