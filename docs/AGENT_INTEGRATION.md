# Agent Integration

Decision Research Agent exposes a small Python Tool Client for upper-layer
agents and automation scripts. The canonical entrypoint is:

```bash
tools/decision_research_agent_tool.py
```

The client wraps the existing HTTP API. It does not store API keys, start the
backend, manage UI sessions, or run benchmark jobs.

For a strict, fail-closed status/result adapter and deterministic compatibility
fixture, see the [Downstream Consumer Contract](reference/downstream-consumer-contract.md).

## Canonical Configuration

| Variable | Purpose | Empty or invalid canonical value |
|---|---|---|
| `DECISION_RESEARCH_AGENT_URL` | API base URL | Empty or whitespace uses `http://127.0.0.1:8000` |
| `DECISION_RESEARCH_AGENT_API_KEY` | Optional `X-API-Key` | Empty explicitly disables the auth header |
| `DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS` | Request timeout | Empty, non-numeric, or non-positive uses `10` |
| `DECISION_RESEARCH_AGENT_ENABLE_BENCHMARK_FIXTURES` | Server-bundled benchmark fixtures | Only `true` enables the provider |
| `DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT` | Talent graph recursion budget | Empty, non-numeric, or non-positive uses the safe default |

Command-line `--base-url` and `--timeout` override environment defaults. API
keys are accepted only through environment variables, not CLI arguments.

Only canonical keys are read. Old aliases and thread-scoped Tool Client
commands were removed with the v0.1.0 runtime cleanup.

## Healthcheck And Doctor

```bash
python tools/decision_research_agent_tool.py healthcheck
python tools/decision_research_agent_tool.py doctor
```

The exact health response remains:

```json
{
  "status": "ok",
  "service": "decision-research-agent"
}
```

Both commands report `service=decision-research-agent`.

`doctor` also checks the controlled durable review runtime. When the feature is
disabled, the durable review check reports `disabled` and the overall command
can still succeed. When enabled, worker, schema, checkpoint compatibility, and
the recorded gate report must be ready.

`doctor` also reports `evidence_verification.status` as `disabled`, `ok`, or
`failed`. The server-side feature remains off unless both controlled runtimes
are explicitly enabled:

```dotenv
DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL=true
DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION=true
```

## Common Commands

Canonical run-scoped execution uses `run_id`:

```bash
python tools/decision_research_agent_tool.py run \
  --query "Research question" \
  --thread-id "demo-thread-001" \
  --wait

python tools/decision_research_agent_tool.py run \
  --query "Research question" \
  --wait \
  --result

python tools/decision_research_agent_tool.py result \
  --run-id "$RUN_ID"
```

Run-specific flags:

```text
--result                     fetch the canonical result after terminal execution
--poll-seconds FLOAT         polling interval, default 1
--wait-timeout-seconds FLOAT total polling deadline, default 600
```

`run` still prints the creation response. `run --wait` polls
`GET /api/runs/{run_id}` until `execution_status` is terminal and still prints
the terminal run projection. `run --wait --result` calls
`GET /api/runs/{run_id}/result` after terminal execution and prints only the
canonical result payload. `--result` without `--wait` performs no request and
returns `result_requires_wait`.

The raw terminal status projection printed by `run --wait` may carry
`failure_cause`. `result --run-id` and `run --wait --result` remain on the
unchanged result contract, including the existing `409 run_failed` envelope
without a cause. No new Tool Client command or model is required.

`run_wait_timeout` is a client polling deadline; it does not cancel the
server-side run. Its structured error includes `run_id` so callers can inspect
the run or use `result --run-id` later. That recovery path also covers
separately created or previously timed-out runs. The client deadline is
distinct from an application-owned terminal `execution/run_timeout` or
`finalization/run_timeout` returned by the status endpoint. For generic runs
the artifact ID is `research-report.md`.

Public repository tests cover the `run --wait --result` golden path with
environment-only API key configuration; captured command output must not
include the API key. Private first-party consumer migration evidence is
deferred unless its own repository test command is run separately. Handoffs for
that external check may record only command names and pass/fail results, not
workspace paths, raw logs, or secrets.

## Controlled Review Commands

The backend requires its controlled review configuration separately. The Tool
Client reads only canonical connection settings:

```bash
export DECISION_RESEARCH_AGENT_URL
export DECISION_RESEARCH_AGENT_API_KEY
export DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS
```

Do not pass an API key on the command line.

```bash
python tools/decision_research_agent_tool.py review list \
  --status waiting_decision \
  --limit 20

python tools/decision_research_agent_tool.py review show \
  --run-id "$RUN_ID"

python tools/decision_research_agent_tool.py review approve \
  --run-id "$RUN_ID" \
  --wait

python tools/decision_research_agent_tool.py review reject \
  --run-id "$RUN_ID" \
  --reason-file "$REJECTION_REASON_FILE" \
  --wait

python tools/decision_research_agent_tool.py review wait \
  --run-id "$RUN_ID" \
  --poll-seconds 1 \
  --wait-timeout-seconds 120

python tools/decision_research_agent_tool.py result \
  --run-id "$RUN_ID"
```

`review show`, `review approve`, `review reject`, and `review wait` accept an
optional `--review-id`. When omitted, the client resolves the current review ID
from the run projection. `review reject` accepts exactly one of
`--reason-file` or `--reason-stdin`; there is no plain `--reason` argument.
`approve` and `reject` derive a deterministic decision ID unless
`--decision-id` is provided.

## Controlled Evidence Verification Commands

These commands use the same canonical URL, API key, and timeout settings. They
do not retrieve sources or perform LLM verification.

```bash
python tools/decision_research_agent_tool.py evidence list \
  --run-id "$RUN_ID" \
  --limit 20

python tools/decision_research_agent_tool.py evidence show \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID"

python tools/decision_research_agent_tool.py evidence verify \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID" \
  --confirm-source-match

python tools/decision_research_agent_tool.py evidence reject \
  --run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID" \
  --reason-code content_mismatch \
  --reason-file "$REASON_FILE"

python tools/decision_research_agent_tool.py evidence finalize \
  --run-id "$RUN_ID"
```

`evidence reject` also accepts `--reason-stdin`. `evidence finalize` reads the
current run state version and creates or reuses a revisioned verification
snapshot/publication before the fresh review workflow.

## Benchmark Process Boundary

`scripts/talent_value_gate_runner.py` temporarily sets the canonical fixture
flag in `os.environ`. It runs profiles sequentially and must not be invoked
concurrently in the same process. The runner restores or removes the temporary
value after success, timeout, or exception.

## Agent Evaluation Regression Gate

The required offline regression gate checks eight fixed scenarios across result,
trajectory, Evidence, terminal-state, safety, and efficiency boundaries:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
```

See the [Agent Evaluation Regression Gate](reference/agent-evaluation-regression-gate.md)
for the `dra.agent-evaluation-cases.v1`, `dra.agent-evaluation-report.v1`, and
`dra.agent-evaluation-comparison.v1` contracts and reviewed baseline workflow.
It must not parse Markdown into typed facts. Pydantic owns structural schemas;
project evaluators own DRA policy. AgentEvals and DeepAgents live evaluation
remain deferred, while LangSmith remains separate diagnostics.

## Error And Security Behavior

The client exits non-zero and prints structured JSON for connection errors,
timeouts, non-2xx responses, malformed JSON, `manual_recovery`, and review wait
timeouts. The minimum envelope always contains `code`, `problem`, `cause`,
`fix`, and `retryable`:

```json
{
  "code": "connection_failed",
  "problem": "Cannot reach Decision Research Agent.",
  "cause": "The configured service endpoint is unavailable.",
  "fix": "Start the backend or verify DECISION_RESEARCH_AGENT_URL.",
  "retryable": true
}
```

Structured server error envelopes retain service-owned fields. When a service
error omits one of the minimum fields, the Tool Client fills only the missing
field with a bounded generic value.

- The API key is never printed.
- The CLI rejects API keys on the command line.
- Rejection reasons are read only from a file or standard input and are not
  echoed by the immediate decision response.
- Actor fingerprints, lease owners, checkpoint paths, and raw tracebacks are
  not printed.
- Use loopback binding unless remote access is intentional.
- The standalone Tool Client reads process environment variables directly; it
  does not load the repository `.env`.
## Lost-response run creation recovery

The `run` command generates one reusable `run-create-<uuid>` identity for each
invocation, or accepts an explicit `--idempotency-key`. There is no automatic retry.
If create returns `request_timeout` or `connection_failed`, retry the
same query/profile/thread/scope and exact key:

```bash
KEY="run-create-$(python -c 'import uuid; print(uuid.uuid4())')"
python tools/decision_research_agent_tool.py run \
  --query "Compare the declared options" \
  --idempotency-key "$KEY"

# Retry only after an ambiguous create failure, with identical inputs.
python tools/decision_research_agent_tool.py run \
  --query "Compare the declared options" \
  --idempotency-key "$KEY"
```

The same request/key returns the original run identity. Changing a canonical
request field under the key returns `409`. The key is replay identity, not
authentication. `status=started` is an acceptance acknowledgement, not an
Agent-start guarantee; read current state through `GET /api/runs/{run_id}`. A
committed run has a private durable dispatch intent, so the single-node worker
recovers handler/process interruption before execution start. Scheduling is
asynchronous: an accepted HTTP 200 keeps the existing response shape even if
the immediate targeted attempt fails. Retry is bounded to three attempts and
stops at `running`; callers should poll rather than infer execution from the
acknowledgement.
