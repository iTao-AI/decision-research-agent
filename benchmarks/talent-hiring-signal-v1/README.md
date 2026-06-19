# Talent Hiring Signal Benchmark v1

This benchmark uses five declared public-job-posting snapshots captured on
2026-06-09. It is intentionally bounded and must not be interpreted as a
market-wide hiring analysis.

Renderer v2 improves the canonical Talent Markdown artifact without changing
the research schema, review authority, service API, or model behavior. Validate
it in this order:

1. deterministic renderer contract, credential-free, normally under 2 minutes;
2. one timed, independent AI-assisted readability review, at most 120 seconds;
3. 1x2 live regression, normally under 10 minutes with a 20-minute ceiling;
4. 3x2 live regression, normally under 30 minutes with a 60-minute ceiling.

Do not spend live research-model time before the first two gates pass. Do not
run 3x2 after a failed 1x2.

## Environment Preflight

Run from the repository root. These checks print variable names and statuses,
not secret values.

```bash
python --version
python -c "import agent.talent_contracts, api.decision_brief, scripts.talent_value_gate_runner"
TMPDIR="${TMPDIR:-/tmp}"
test -d "$TMPDIR" && test -w "$TMPDIR"

PRIMARY_REPO="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
ENV_FILE="$PRIMARY_REPO/.env"
test -f "$ENV_FILE"
python -m dotenv -f "$ENV_FILE" run -- python -c '
import os
required = ("OPENAI_BASE_URL", "OPENAI_API_KEY")
missing = [name for name in required if not os.getenv(name)]
model_present = bool(os.getenv("LLM_MODEL") or os.getenv("LLM_QWEN_MAX"))
print("required_names_present=" + str(not missing and model_present).lower())
raise SystemExit(0 if not missing and model_present else 1)
'
```

If Python cannot create temporary files, set `TMPDIR` to a verified writable
directory before treating the failure as a project regression.

## Gate 1: Deterministic Renderer

This gate needs no model credentials and is the first proof to run:

```bash
python -m pytest \
  tests/unit/test_decision_brief.py \
  tests/unit/test_profile_registry.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_talent_value_gate_runner.py -q
```

The fixed input is
[`tests/fixtures/talent-decision-brief-renderer-v2.json`](../../tests/fixtures/talent-decision-brief-renderer-v2.json).
The byte-exact expected artifact is
[`tests/fixtures/talent-decision-brief-renderer-v2.md`](../../tests/fixtures/talent-decision-brief-renderer-v2.md).

Never auto-update the golden file after a mismatch. Inspect the diff and update
it only after an approved renderer contract change.

## Gate 2: Timed Independent Readability

Use
[`renderer-v2-readability-scorecard.md`](renderer-v2-readability-scorecard.md).
A fresh, read-only AI session receives only the fixed golden Markdown and five
questions. It must score 5/5 within 120 seconds. Do not open JSON, source code,
tests, or the separate answer key while timing the review. Record the role as
`ai-assisted-independent-reviewer`; do not describe this evidence as human
review.

The owner does not need to complete a second scorecard. Owner confirmation is a
brief final delivery check after the deterministic and live gates.

## Gate 3: 1x2 Live Regression

```bash
python -m dotenv -f "$ENV_FILE" run -- \
  python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 1 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-1x2.json
```

Required result:

- `expected_run_count=2` and `completed_run_count=2`;
- `completion.ready_for_human_review=true`;
- every readiness failure counter is `0`;
- `renderer_contract_failure_count=0`;
- Talent JSON declares `renderer_version="2"` and Talent Markdown exactly
  matches deterministic rendering of that JSON.

The CLI writes the bundle and prints its path even on failure. An incomplete
bundle exits `1`; inspect the saved diagnostics before retrying.

## Gate 4: 3x2 Live Regression

Run only after Gate 3 passes:

```bash
python -m dotenv -f "$ENV_FILE" run -- \
  python scripts/talent_value_gate_runner.py \
  --scope benchmarks/talent-hiring-signal-v1/research-scope.json \
  --fixture benchmarks/fixtures/talent-hiring-signal-v1.json \
  --repetitions 3 \
  --per-run-timeout-seconds 600 \
  --output /tmp/decision-research-talent-renderer-v2-3x2.json
```

Required result: six completed runs, `ready_for_human_review=true`, and every
readiness failure counter remains `0`. This proves end-to-end stability only;
it is not a new readability or market-value experiment.

## Failure Guide

| Signal | Meaning | Next action |
|---|---|---|
| Golden mismatch | Renderer bytes changed | Inspect the diff; do not auto-update the fixture |
| Temp directory error | Python/pytest cannot create temporary files | Set a verified writable `TMPDIR` and rerun Gate 1 |
| Missing `.env` or model variable | Live model cannot initialize | Select the primary checkout `.env`; verify names only |
| `runner_timeout` | One profile exceeded its per-run limit | Inspect the recorded profile/repetition before retrying |
| `renderer_contract_failure_count` | Talent artifacts are missing, malformed, v1, hash-invalid, or Markdown-mismatched | Inspect `decision-brief.json` and `.md`; do not run 3x2 |
| Other readiness counter | Research, evidence, identity, or profile contract failed | Inspect the failed run and existing counter definition |
| AI-assisted readability score below 5/5 | The hierarchy is not reliably scannable | Revise copy/layout and use a fresh independent session |

One failed Talent run can increment several independent counters.

## Versioning And Rollback

- Renderer v2 changes presentation bytes and the canonical semantic hash of new
  Talent briefs because `renderer_version` participates in canonical hashing.
- `generated_at` can change Markdown bytes without changing that semantic hash.
- Existing renderer-v1 and renderer-v2 artifacts are immutable and are never
  migrated or rerendered.
- Roll back renderer code and the profile `renderer_version` together. Reverting
  only the version constant is not valid.

## Fair Comparison Boundary

The runner gives `generic` and `talent-hiring-signal` the same byte-stable
prompt envelope. It measures profile behavior on identical snapshot input; it
does not measure live-search quality. The runner always emits
`value_gate.passed=false`; human value decisions remain separate.

The exported bundle contains paired results, evidence, Talent
`ResearchPacket`, deterministic review, and canonical DecisionBrief artifacts.
It excludes runtime filesystem paths and redacts secret-like exception text.

## Advanced Service Fixture Boundary

- `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES=true` explicitly enables
  the service fixture provider; it is disabled by default.
- The provider resolves only the aggregate ID declared in validated
  `ResearchScope` and never accepts file paths.
- The standalone runner enables the bounded provider only for each Talent run
  and restores the prior process value afterward.
- Do not run the offline comparison inside a concurrently serving API worker.

## Limitations

- Source URLs may expire or redirect to access-verification pages.
- The bundled fixture preserves a concise source-backed snapshot; it does not
  claim the jobs remain open.
- Five selected postings do not represent overall demand, salary trends, or
  hiring volume.
- Human scores remain reviewer judgments, not automatic quality metrics.
