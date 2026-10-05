# Read-only findings CLI and independent consumer

Use an existing `generic-evidence-report@1` run. These commands read delivery;
they do not create/retry runs, poll, approve, verify Evidence or call a model.
The application-owned persisted findings/result readers retain authority.

## Read JSON or canonical Markdown

```bash
mkdir -p output
python tools/decision_research_agent_tool.py \
  --base-url http://127.0.0.1:8000 --timeout 10 \
  findings --run-id "$RUN_ID"

python tools/decision_research_agent_tool.py \
  --base-url http://127.0.0.1:8000 --timeout 10 \
  findings --run-id "$RUN_ID" --format markdown > output/report.md
```

Global flags precede `findings`; `--format` accepts `json` (default) or
`markdown`. The client reads the process environment directly:
`DECISION_RESEARCH_AGENT_URL`, `DECISION_RESEARCH_AGENT_TIMEOUT_SECONDS`, and
optional `DECISION_RESEARCH_AGENT_API_KEY` (`X-API-Key`). It does not load `.env`
or accept credentials as CLI flags.

For **findings only**, a nonempty timeout must be finite and
`0 < timeout <= 60` seconds; omitted timeout uses 10. The endpoint must be an
absolute ASCII HTTP(S) URL, at most 2048 characters, with a host/valid port and
no credentials, query, fragment, whitespace or control characters. A service
path prefix is allowed. The optional key must be printable ASCII without
whitespace, at most 4096 characters. Run IDs must be nonblank, at most 500 code
points, without control characters; they are encoded as one path component.
Existing commands retain their previous configuration behavior, including
invalid-timeout fallback.

JSON performs GET `/api/runs/{run_id}/findings`, then GET
`/api/runs/{run_id}`. The output preserves all fields of the findings response
and adds three status observations:

| Field | Meaning |
| --- | --- |
| `run_id`, `execution_status`, `delivery_status` | Requested run, completed/ready delivery |
| `artifact` | Canonical JSON ID/kind/media type/content/own-byte hash |
| `report` | Unchanged `dra.research-findings.v1` report, accepted questions, source-bound findings and dispositions |
| `evidence` | Actual public same-run Evidence rows, including citation and verification status |
| `review_status`, `review_decision` | Actual public review observations, copied without granting verification |

The client checks identity/profile, accepted scope questions, artifact/report
agreement and reference-to-Evidence agreement. The two reads are observations;
they are not an atomic review/verification snapshot. Inconsistent delivery
data fails closed. Keep unresolved dispositions and their reasons, limitations
and model-reported contradictions when presenting the report. An approved run
can still contain `verification_status=unverified` Evidence.

Markdown performs the findings read first, then GET `/api/runs/{run_id}/result`.
It requires the structured profile and `research-report.md` with kind
`research_findings_markdown`. Stdout contains the exact stored UTF-8 content,
with no client rendering or extra newline. It cannot fall back to legacy
generic Markdown. Both JSON and Markdown stdout use UTF-8 regardless of the
process's text encoding.

## Errors and bounds

Only GETs are sent. Neither redirects nor retries are followed. Successful
HTTP bodies are at most `4 * 1024 * 1024 + 65536` bytes, error bodies at most
65536 bytes, and each artifact's content at most 1 MiB. JSON parsing rejects
invalid UTF-8, duplicate keys, nonfinite values and escaped lone surrogates.
Each network operation has the configured timeout; streaming reads also check
a request deadline. Each of the two requests is bounded by at most twice the
timeout, excluding local process startup.

Success exits 0. Service/transport/client failures are JSON on stdout and exit
1. Invalid CLI syntax exits 2 with argparse usage on stderr.

| Code | Read outcome |
| --- | --- |
| `run_not_found` | Existing run absent (HTTP 404) |
| `run_not_terminal` | Pending/running (HTTP 409); no automatic wait |
| `run_failed`, `run_review_required`, `run_delivery_blocked` | Existing terminal/delivery restriction (HTTP 409) |
| `run_result_unavailable` | Wrong profile, missing/corrupt artifact, invalid binding or unavailable delivery (HTTP 409) |
| Existing access-policy codes, e.g. `api_key_invalid` | Authentication/authority failure |
| `findings_config_invalid` | Invalid findings-only configuration before HTTP |
| `findings_response_invalid` | Inconsistent successful delivery/status/artifact |
| `invalid_json_response`, `json_response_not_object`, `response_too_large` | Unsupported or oversized response |
| `request_timeout`, `connection_failed` | Bounded transport failure |

No error becomes an empty success, raw candidate or generic result. Source URLs
are observed report values; these commands do not fetch them.

## Separate consumer process

```bash
mkdir -p output
python scripts/research_findings_consumer.py \
  --base-url http://127.0.0.1:8000 --timeout 10 \
  --run-id "$RUN_ID" --output output/findings-receipt.json
```

The consumer uses only the standard library and launches the real Tool Client
as a child with the current Python interpreter. The CLI reads the public HTTP
service. The consumer never imports server/producer/report validator modules,
reads the database, workspace, VFS candidate or trace, or re-renders Markdown.
The output's parent directory must exist; an existing file is refused before
starting the child. Exclusive publication also protects against a file created
while consumption is running. A failed write leaves no partial receipt.

The `dra.research-findings-consumption.v1` receipt is UTF-8 JSON on stdout and
in the required output file, at most 256 KiB. It includes run/profile and
delivery/review observations, JSON artifact ID/hash/byte count, question IDs,
dispositions/reasons/finding IDs, reference identities/source URLs/offsets and
actual citation/verification states, reported contradictions and limitations.
It omits full statements, snippets and artifact content. Its checks record
own-byte hash/report agreement, run/profile identity, question coverage,
same-run Evidence binding, exact code-point offsets and public HTTPS URL
admission. They do not measure truth, entailment or research quality.

The child deadline is `4 * timeout + 10` seconds, at most 250 seconds, and child
stdout is accepted only up to 8 MiB. There is no retry. Existing CLI/service
error codes are propagated. Local codes are `consumer_timeout`,
`consumer_process_failed`, `consumer_response_invalid`,
`consumer_delivery_invalid` and `consumer_output_failed`. Failed consumption
exits 1 with a bounded error and creates no receipt; syntax errors exit 2.
Child stderr and raw exceptions are not exposed.

## Reproduce the provider-free process/HTTP boundary

In an existing locked Python 3.11 environment, start this temporary service in
one terminal:

```bash
PYTHON_DOTENV_DISABLED=1 LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
  python scripts/research_evidence_delivery_proof.py serve \
  --origin http://127.0.0.1:5175 --port 8876 --seconds 180
```

In another terminal, run the consumer against
`http://127.0.0.1:8876` with one of the declared run IDs in the
[operations walkthrough](../operations/research-evidence-delivery.md). Complete,
partial and contradictory cases produce receipts. Partial retains its unresolved
question; contradictory retains two references and one model-reported
contradiction. Insufficient Evidence remains completed/blocked, returns
`run_delivery_blocked` and produces no receipt. Ctrl-C stops the owned service;
its timer also expires automatically.

`serve` prints monitor progress before its startup JSON containing `api` and
`cases`. Select that metadata line or the displayed run IDs; do not parse the
first stdout line as JSON. This local process/HTTP method was verified on
2026-10-05. A successful consumer exits 0 and creates its checked receipt;
the blocked case exits 1 with its service code and no receipt.

The producer uses a programmed tool-calling model and declared search fixture
inside the installed graph, with real execution/finalization/persisted readers.
The positive consumer test uses a server process, CLI process and separate
consumer process over actual loopback HTTP. Controlled DB/HTTP fixtures cover
negative states and tampering; they do not replace that positive chain.
This proves deterministic plumbing and structural consumption, not autonomous
research, paid-provider behavior or semantic value.

```bash
python -m pytest -q tests/unit/test_research_findings_tool.py \
  tests/unit/test_research_findings_consumer.py \
  tests/integration/test_research_findings_consumer_journey.py
```

The existing [generic downstream contract](downstream-consumer-contract.md)
and its `scripts/downstream_consumer_contract.py` fixture remain separate and
unchanged. This feature adds no MCP server or SDK.
