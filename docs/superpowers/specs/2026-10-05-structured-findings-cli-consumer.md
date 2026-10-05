# Read-only structured findings CLI and consumer

## Approved scope

Expose an existing `generic-evidence-report@1` run through the Tool Client and
an independent, stdlib-only downstream consumer. Delivery authority remains
`resolve_run_findings` and the existing persisted result reader. This slice
does not create, retry, wait for, approve or verify runs, invoke a model, alter
Evidence identity, or change any REST/schema/persistence contract.

The delivery owner may settle implementation details within this scope and
complete local commits and verification. Hosted delivery requires separate
authorization. Start from clean main `243a1e935e5ec138b0c68a755345582f69d28940`
in an isolated `codex/findings-cli-consumer` branch. Keep existing generic CLI
commands and `scripts/downstream_consumer_contract.py` behavior unchanged.

## Tool Client interface

```bash
python tools/decision_research_agent_tool.py --base-url http://127.0.0.1:8000 \
  --timeout 10 findings --run-id RUN_ID [--format json|markdown]
```

Global flags precede the subcommand. JSON is the default. Existing environment
keys supply endpoint, optional `X-API-Key` and timeout. On this command only,
nonempty timeout configuration must be finite, greater than zero and at most
60 seconds; an omitted value uses 10 seconds. The endpoint must be an absolute
ASCII HTTP(S) URL of at most 2048 characters, without credentials, query,
fragment or control/whitespace characters, with an IP literal or valid DNS host
and port. Raw endpoint whitespace is rejected, not trimmed. A path
prefix is allowed. A nonblank run ID is valid UTF-8, at most 500 code points, contains no
control characters and is encoded as one URL path component. Invalid
configuration returns `findings_config_invalid` before network access.

JSON reads `/api/runs/{run_id}/findings` first, then the existing run status.
It preserves the findings envelope fields `run_id`, `execution_status`,
`delivery_status`, `artifact`, `report` and adds exactly `evidence`,
`review_status`, `review_decision` copied from that same run's public status.
The report, canonical JSON content and metadata are unchanged. Check run and
profile/version identity, ready/completed state, accepted scope questions,
artifact hash/content/report agreement and reference-to-public-Evidence
agreement. Verification status comes from each actual Evidence row; approval
never upgrades it. The two reads are observations, not an atomic snapshot of
review or verification activity. Mismatched delivery data fails closed.

Markdown reads findings first, then `/api/runs/{run_id}/result`. Require the
structured profile, same run/ready state and canonical artifact
`research-report.md`, kind `research_findings_markdown`, media `text/markdown`,
own-byte hash and 1 MiB content bound. Emit precisely the stored UTF-8 content,
without client rendering or an extra newline. The first reader prevents a
legacy generic result from becoming a structured findings fallback.

Both formats perform only GETs, without redirects or retries. Successful
responses are bounded to `4 * 1024 * 1024 + 65536` bytes and error responses to
65536 bytes. Each GET uses a short-lived transport worker and an absolute
request deadline covering DNS, connection, TLS, headers and body; local worker
startup is separately bounded to five seconds. Expired workers are terminated
and reaped. Streaming body reads also check the deadline. JSON stdout, including
indentation expansion, is bounded to 8 MiB before any success output. UTF-8 and JSON must
be valid, with no duplicate keys or nonfinite values. Malformed replies return
`invalid_json_response`, malformed HTTP status/framing `invalid_http_response`,
oversized replies/output `response_too_large`, and inconsistent
delivery data `findings_response_invalid`. Existing service error codes and
transport errors are retained. Success exits 0; errors are bounded JSON on
stdout and exit 1; argparse usage errors exit 2. Findings stdout is UTF-8 even
when the process's text encoding differs.

## Independent consumer interface and receipt

```bash
python scripts/research_findings_consumer.py --base-url http://127.0.0.1:8000 \
  --timeout 10 --run-id RUN_ID --output output/findings-receipt.json
```

The consumer imports only the Python standard library. It invokes the real
Tool Client in a separate subprocess using the current Python interpreter;
that CLI reaches the real public HTTP service. It never imports producer,
server, repository, framework or report validation/rendering modules and never
reads a database, VFS candidate, workspace or trace. Inherited credentials go
only to the CLI environment. Its child deadline is `4 * timeout + 10` seconds,
with a maximum of 250 seconds. Invalid CLI configuration remains a bounded
failure. Child stdout is counted during collection and capped at 8 MiB; a size
or deadline breach stops the child and, on POSIX, its process group, even if the
parent has already exited. Child nonzero/invalid JSON/invalid UTF-8/oversized output/timeout never
produces a success receipt. The consumer does not expose child stderr or raw
exceptions.

Independently validate the delivered JSON artifact's UTF-8 own-byte hash,
parsed report agreement, schema/run/profile, unique accepted question IDs,
dispositions/coverage, finding IDs, exact Unicode code-point offsets and
same-run Evidence IDs/fingerprints/source identity/snippets. Source URLs must
satisfy the existing public HTTPS URL policy; validation never fetches them.
Preserve reported contradictions, unresolved reasons and actual citation and
verification states; do not infer semantic support or quality from structure.

The bounded receipt has schema `dra.research-findings-consumption.v1`, run and
profile identity, execution/delivery/review observations, JSON artifact ID and
hash, question IDs/dispositions/reasons/finding IDs, reference identities,
actual verification/citation states, reported contradictions, limitations and
explicit structural checks. It omits full statements, snippets and artifact
content. Checks describe only performed structural validation; there is no
truth, entailment, quality score or human value gate. The output is UTF-8 JSON
at most 256 KiB, created exclusively at the required path. Existing files are
not overwritten. No receipt is written on failed consumption. Local failures
use fixed machine codes `consumer_timeout`, `consumer_process_failed`,
`consumer_response_invalid`, `consumer_delivery_invalid`, `consumer_output_failed`;
an existing Tool Client/service error is propagated with its code.

## Observable acceptance

- Real CLI subprocess -> loopback HTTP -> authoritative persisted reader ->
  separate consumer process succeeds for the declared native fixture's
  complete, partial and contradictory cases. Partial remains 2 questions / 1
  unresolved; contradictory retains two bound references and one model-reported
  contradiction. Insufficient Evidence remains completed/blocked with
  `run_delivery_blocked` and no receipt.
- JSON matches direct public findings/report bytes and public Evidence states;
  Markdown stdout matches the exact stored bytes and hash, including Unicode.
- Pending, failed, review-required, missing, wrong-profile, missing artifact,
  hash-invalid and binding-invalid states preserve existing error codes.
  Cross-run references, invalid offsets, illegal URLs and rehashed tampering
  remain rejected by the actual persisted reader. Approval plus unverified
  Evidence is reported as unverified, using a declared negative-control fixture.
- Configuration, authentication, response bounds, timeout, invalid UTF-8,
  subprocess failure and output-file failures have bounded outcomes. Legacy
  Tool Client and generic consumer regressions stay green.
- Update the operations walkthrough, Agent Integration, a dedicated CLI usage
  reference and README navigation. Run focused regressions and the full backend
  non-Docker suite. No frontend code/docs or durable HITL behavior changes.

The existing native producer fixture uses a programmed model and declared
search sources inside the installed graph. It proves that deterministic path,
not autonomous research or semantic quality. Positive consumer proof requires
the real process/HTTP chain above; fake HTTP and controlled DB mutations are
negative controls only. Do not run real providers or paid acceptance, or
inspect or change separately retained quality-stage material.
