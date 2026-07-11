# Downstream Consumer Contract

This reference defines a conservative, offline compatibility boundary for an
Agent or workflow that consumes existing Decision Research Agent run and result
responses. The fixture schema is `dra.downstream-consumer.v1`. The reference
script is a proof, not a packaged SDK or production service, and it adds no
runtime endpoint or business authority.

## Request Sequence

1. Confirm `GET /health` returns
   `{"status":"ok","service":"decision-research-agent"}`.
2. Create or receive a `run_id`, then poll `GET /api/runs/{run_id}`. A client
   timeout stops only client polling; it does not cancel the server run.
3. Read the typed execution, review, and delivery states before requesting
   `GET /api/runs/{run_id}/result`.
4. Validate the result code and, for a successful generic result, validate the
   complete artifact boundary below before using it as draft input.

Build and check the deterministic fixture with Python 3.11:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py build \
  --output docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
```

A breaking proof-schema change requires a new schema version and fixture file.
Additive upstream API fields are ignored unless a later fixture version
explicitly projects them.

## State And Disposition

| Execution / review / delivery | Result | Classification | Disposition |
|---|---|---|---|
| `pending/not_required/pending` | `run_not_terminal` | `supported` | `wait` |
| `running/not_required/pending` | `run_not_terminal` | `supported` | `wait` |
| `completed/not_required/ready` | canonical generic artifact | `supported` | `accept_draft` |
| `completed/not_required/ready` | fallback artifact | `partial` | `block_fallback` |
| `completed_with_fallback/not_required/ready` | fallback artifact | `partial` | `block_fallback` |
| `completed/required/review_required` | `run_review_required` | `supported` | `await_review` |
| `completed/resolved/blocked` | `run_delivery_blocked` | `supported` | `block` |
| `failed/not_required/failed` | `run_failed` | `supported` | `block` |
| `completed/not_required/ready` | `run_result_unavailable` | `supported` | `block` |

`accept_draft` permits downstream draft synthesis only. It is not approval,
publication, or Evidence verification. `accept_draft` content remains
untrusted. A fallback is always blocked, even when delivery is `ready`.

Every current `409` result envelope may report `retryable=true`. That flag does
not override failed, review-required, or blocked state. Retry only pending or
running work after polling status. Review-required work waits for the governed
review workflow; blocked and failed work stays blocked. An unavailable result
can be retried only after a newer status projection establishes a valid state.

## Generic Artifact Validation

A generic canonical artifact is accepted as draft input only when all of these
checks pass:

- execution is `completed`, review is `not_required`, and delivery is `ready`;
- `artifact_id` is `research-report.md`;
- `kind` is `research_report_markdown`;
- `media_type` is `text/markdown`;
- UTF-8 content is non-empty and no larger than 1 MiB;
- `content_hash` is lowercase SHA-256 of the exact UTF-8 content.

`research_report_fallback_markdown` always maps to `block_fallback`.
`completed_with_fallback` is compatibility input, not the active generic
fallback signal. Profile-specific `decision_brief_markdown` hash semantics are
outside this generic v1 validator and fail closed.

## Evidence And Capability Boundary

The fixture projects run-level Evidence through this exact allowlist:

```text
evidence_id
source_url
source_identity
retrieved_at
citation_status
verification_status
```

`source_url` may be null; fixture URLs are public HTTPS URLs without userinfo.
`verification_status` is a compatibility field and does not prove who verified
a source or establish a human approval. `retrieved_at` records retrieval time,
not an official source effective date.

The `supported` list covers run state, run-level Evidence, generic canonical
artifacts, fallback distinction, review/delivery gates, and stable result
errors. The `partial` list records retrieval-time limits, fallback content, and
the compatibility-only fallback execution status.

The `unknown` list deliberately includes claim-level Evidence references,
typed limitations, typed conflicts and gaps, source title/publisher/effective
date, persistent failure cause, and persistent usage/cost. Consumers must not parse Markdown
to manufacture typed claims, limitations, conflicts, dates, or Evidence
references. Markdown headings and prose do not add typed contract fields.

## Authority And Failure Handling

The application database remains authoritative for ResearchRun,
EvidenceLedger, review, verification, publication, and delivery. A LangGraph
checkpoint stores workflow position; it is not a consumer ledger. A LangSmith
trace is privacy-first diagnostic data; it is not business authority.

The proof CLI fails closed with bounded codes such as
`contract_file_invalid`, `contract_schema_unsupported`,
`contract_schema_invalid`,
`contract_state_invalid`, `contract_result_invalid`,
`contract_artifact_invalid`, `contract_evidence_invalid`, and
`contract_fixture_drift`. It does not print requested paths, fixture content,
raw exceptions, or tracebacks.
