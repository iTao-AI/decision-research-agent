# Strict Citation Profile

`generic-strict-citation@1` is an opt-in finalization policy for callers that
need ready delivery to contain at least one exact admitted URL from current-run
source Evidence. It reuses the generic research runtime and changes only the
application-owned delivery invariant.

The producer-pin identity for this profile is:

```text
profile_id="generic-strict-citation"
profile_version="1"
proof_schema="dra.strict-citation-profile.v1"
```

The proof schema is documented producer identity. It is not a manifest or
result field, and the API does not expose a profile-list endpoint.

## Choose

Use literal `generic` for backward-compatible behavior: zero exact citations
remain warning-only and a non-empty canonical report may become ready. Choose
`generic-strict-citation` only when ready must prove an exact current-run
source URL is present. Talent profile behavior is unchanged.

## Discover

Read the exact server-owned profile and version:

```http
GET /api/profiles/generic-strict-citation
```

The response uses the existing single-profile manifest shape and reports
profile version `"1"`. It does not enumerate profiles, return
`dra.strict-citation-profile.v1`, or add a proof-schema field.

## Run

Use the existing `profile_id` request field:

```http
POST /api/runs
Content-Type: application/json

{
  "query": "Research question",
  "profile_id": "generic-strict-citation",
  "scope": {}
}
```

The existing Tool Client option follows the same path:

```bash
python tools/decision_research_agent_tool.py run \
  --profile generic-strict-citation \
  --query "Research question" \
  --wait \
  --result
```

No new command, environment variable, request field, response field, database
field, status, artifact kind, or failure code is introduced.
There is no new request, response, database, status, artifact, or failure
field.

## Interpret

The generic DeepAgents graph runs first and independently freezes current-run
Evidence. Application finalization then builds the canonical non-fallback
report and recomputes exact URL citations.

- If the initial artifact already contains an exact admitted URL, finalization
  succeeds with zero correction calls.
- Otherwise the application may prepare and perform at most one
  application-level direct semantic placement call.
- The model selects only application-issued target and source IDs. The
  application owns exact URL bytes, Markdown insertion, artifact rebuilding,
  citation recomputation, persistence, and terminal state.
- Ready proves at least one exact admitted URL from current-run source Evidence
  is present in the final canonical non-fallback artifact after application
  recomputation.

The correction call occurs after generic graph execution. Its zero/one-call
bound is separate from, and is not consumed or measured by, the generic
harness model, tool, token, or recursion middleware budgets. “One call” means
one application invocation; it does not claim one provider transport request.
The configured model wrapper continues to own any transport retry or fallback
behavior it already provides.

The result endpoint and canonical `research-report.md` artifact shape remain
unchanged.

## Troubleshoot

Read the existing status projection:

```http
GET /api/runs/{run_id}
```

An ordinary strict finalization failure is
`failed / not_required / failed` with
`finalization/run_finalization_failed`. Current-run Evidence remains available,
but no ready or partially corrected artifact is exposed. The unchanged result
endpoint returns `409 run_failed`.

Operators may see one closed `strict_citation_*` category in the existing task
log to distinguish local source, target, packet, model, response, artifact, or
invariant failures. REST deliberately keeps the coarser public cause. Neither
diagnostic is a new result or consumer field, and neither exposes the packet,
model response, provider diagnostic, or exception body. Do not retry
correction inside the same run.

Existing timeout and cancellation classifications take precedence:
`finalization/run_timeout` and `finalization/cancelled`.

## Cost And Data Boundary

The correction branch sends bounded target excerpts, admitted public URLs, and
bounded source snippets to the run's configured model. Report excerpts and
snippets are treated as untrusted data. Paragraphs or snippets matching the
documented obvious credential, diagnostic, or host-path markers are omitted
or replaced with `[context omitted]`.

This bounded marker filter is not credential scanning or a
data-loss-prevention system and makes no local-only processing claim.
Configured tracing, retry, fallback, and provider transport remain
operator/runtime concerns. Provider-free tests prove deterministic application
behavior; they do not prove live-provider reliability.

## Pin Intentionally

A consumer accepts this capability only after intentionally pinning:

```text
repository + release/tag-or-commit + profile_id + profile_version + proof_schema
```

| Situation | Consumer action |
| --- | --- |
| Existing consumer keeps literal `generic` | Keep its current producer pin and warning-only semantics |
| Consumer opts into strict v1 | Pin and validate a new strict producer identity |
| An unrelated future DRA version lands | No automatic consumer change |
| A coherent future Release is published | Evaluate and pin it only if the consumer needs its contract |

A DRA version change does not automatically require a consumer upgrade.
`dra.downstream-consumer.v1` and the v0.1.6 fixture remain unchanged.
Release remains a separate decision; this is not claimed as v0.1.6.

## Non-Claims

Strict ready does not prove citation correctness, citation completeness,
source truth, source quality, entailment, universal model compliance,
live-provider reliability, one provider request, hosted observability,
business impact, downstream adoption, or publication in a Release. It proves
only the bounded opt-in application behavior stated above.
