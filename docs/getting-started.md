# Getting Started

This tutorial starts the Python 3.11 backend, verifies the service, and uses
the first-party Tool Client to create and retrieve one canonical research run.

## Prerequisites

- Python 3.11
- Git
- Provider credentials for a real research run

Keep credentials in `.env`. Do not pass API keys on the command line or commit
the environment file.

## 1. Create The Environment

From the repository root:

```bash
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps -r constraints.txt
```

Edit `.env`. At minimum, configure the selected model provider. Configure
`TAVILY_API_KEY` when the run needs public web search. If `API_SECRET` is set,
also export the same value for the Tool Client:

```bash
export DECISION_RESEARCH_AGENT_API_KEY="replace-with-your-local-secret"
```

## 2. Start The Backend

```bash
python api/server.py
```

Leave this terminal running.

## 3. Verify Health

In a second terminal with the virtual environment active:

```bash
curl --fail --silent http://127.0.0.1:8000/health
```

Expected result:

```json
{"status":"ok","service":"decision-research-agent"}
```

## 4. Check Integration Readiness

```bash
python tools/decision_research_agent_tool.py doctor
```

`doctor` returns structured JSON. Required failures include a bounded cause and
fix; optional disabled workflows do not block a generic run.

## 5. Create A Canonical Run

```bash
python tools/decision_research_agent_tool.py run \
  --query "Compare the documented trade-offs of two implementation options" \
  --thread-id "getting-started" \
  --wait
```

The JSON response includes a generated `run_id`, terminal execution state, and
delivery state. Copy the returned identifier:

```bash
export RUN_ID="run_replace_with_returned_id"
```

## 6. Retrieve The Result

```bash
python tools/decision_research_agent_tool.py result --run-id "$RUN_ID"
```

A ready generic run returns the persisted Markdown artifact with its ID, kind,
media type, content hash, and content. The command does not read a local output
path or framework checkpoint.

## Troubleshooting

### Provider configuration is missing

Set the provider URL, model name, and API key in `.env`, then restart the
backend. Use `doctor` to distinguish provider configuration from optional
review or verification flags.

### Authentication returns 401

When `API_SECRET` is set on the backend, set
`DECISION_RESEARCH_AGENT_API_KEY` to the same local secret before running the
Tool Client. Do not put it in shell history as a command argument.

### The run is not terminal

`run_not_terminal` means execution is still pending or running. Re-run the
`run --wait` flow or poll `GET /api/runs/{run_id}` before requesting the
result.

### The result requires review

`run_review_required` means the current Talent publication is not deliverable
until the default-disabled controlled review workflow resolves it. Follow the
[Controlled Review](operations/controlled-review-workflow.md) runbook in an
authorized environment; approval permits delivery but does not verify
Evidence.

### The artifact is unavailable

`run_result_unavailable` indicates a missing, empty, unsafe, oversized, or
hash-mismatched persisted artifact. Preserve the run identifier and inspect
bounded service diagnostics. Do not bypass result selection by reading runtime
files or checkpoint state.
