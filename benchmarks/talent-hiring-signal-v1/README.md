# Talent Hiring Signal Benchmark v1

This benchmark uses five declared public-job-posting snapshots captured on
2026-06-09. It is intentionally bounded and must not be interpreted as a
market-wide hiring analysis.

## Fair Comparison

The offline value-gate runner gives `generic` and `talent-hiring-signal` the
same byte-stable prompt envelope. It measures profile behavior on identical
snapshot input; it does not measure live-search quality.

The runner does not add `provided_aggregate` to the Generic profile, change any
service API, or expand production permissions.

Run from the repository root with valid model configuration:

```bash
python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --output output/benchmarks/talent-hiring-signal-v1.json
```

The output contains paired raw results, evidence, Talent `ResearchPacket`,
deterministic review bundle, and canonical DecisionBrief artifacts. It excludes
runtime filesystem paths and redacts secret-like exception text.

## Review Procedure

1. Confirm `completion.ready_for_human_review=true`.
2. Blind-review each paired result without using the profile label.
3. Score evidence coverage, scope adherence, limitations, and reviewability
   from 0 to 2.
4. Compare paired scores across all repetitions.
5. Record the human decision separately. The runner always emits
   `value_gate.passed=false` and cannot approve the P1A value gate.

Any failed run, missing Talent packet, missing Talent artifact, mismatched input
hash, invalid Profile pair, or reused run identity keeps
`benchmark_status=incomplete`. Evidence URLs outside the bundled fixture are
counted by Profile and remain available for the human scope-adherence score.
Completion counters are independent diagnostics, so one failed Talent run may
increment both `schema_failure_count` and `artifact_failure_count`.

## Service Fixture Boundary

- Set `DEEP_SEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES=true`.
- Submit `research-scope.json` with `profile_id=talent-hiring-signal`.
- The `provided_aggregate` tool can resolve only the aggregate ID declared in
  that validated scope.
- The fixture provider is disabled by default and never accepts file paths.

These settings apply to service-level Talent smoke tests. They are not required
by the offline fair-comparison runner. The runner enables the bounded fixture
provider only while executing each Talent run and restores the previous setting
afterward. Run it as a standalone process, not inside a concurrently serving API
worker.

## Limitations

- The source URLs may expire or redirect to access-verification pages.
- The bundled fixture preserves a concise source-backed snapshot for repeatable
  comparison; it does not claim the jobs remain open.
- Five selected postings do not represent overall demand, salary trends, or
  hiring volume.
- Manual scores remain reviewer judgments and must not be presented as automatic
  quality metrics.
