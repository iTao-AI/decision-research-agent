# Evidence Source Admission Closure Design

Status: Approved

## Purpose

Close the producer-side gap between search output, generic Evidence capture,
the downstream compatibility validator, and the bounded-live Evidence receipt.
The change is provider-free and preserves the existing application authority
model.

## Problem

The search boundary previously returned every provider result row to the model
and monitor. The generic stream observer also treated arbitrary outer
`ToolMessage` values as Evidence-capable. As a result, an HTTP URL or a URL from
an outer task summary could enter application Evidence even though later
bounded-live contracts rejected it.

The Tavily Python response contract types each result URL as a string; it does
not guarantee the repository's publishable public-source policy.

## Decisions

### One producer URL policy

`agent/source_url_policy.py` owns a pure, network-free predicate for
publishable source URLs. It accepts only bounded canonical ASCII HTTPS URLs
with a public DNS hostname, no credentials, no query or fragment, and no port
other than 443. IP literals, localhost variants, `.local`, `.internal`,
trailing-dot hosts, malformed percent escapes, control characters, Unicode,
and oversized values fail closed.

The producer does not resolve DNS and does not normalize an unsafe value into
a different source identity. It must drop the complete result row without
rewriting its URL.

### Earliest search boundary

The Tavily wrapper filters a copied provider response before the result reaches
the model, cache consumer, or `monitor.report_end()`. Accepted rows keep their
fields and deterministic order. Malformed response shapes and over-bound
result lists become an empty accepted result set without exposing rejected
values.

### Exact source authority

Only the exact `network_search` / `internet_search` pair can create generic
tool-derived Evidence. Outer `task` summaries, file tools, database tools,
knowledge-base tools, arbitrary subagent text, and other tool messages have no
source authority even when they contain URL-shaped text.

The `provided_aggregate` preload remains a separate application-owned declared
fixture path. It does not grant generic outer tool messages Evidence authority.

### Defense in depth and implication

`extract_evidence_entries()` applies the same admission predicate so direct
callers cannot bypass the Tavily boundary. The bounded-live `EvidenceReceipt`
uses the same pure predicate.

The downstream consumer validator remains independently implemented. The
executable contract is: every producer-admitted URL implies downstream and
Evidence receipt acceptance. The producer may remain a strict subset of the
downstream compatibility surface.

### Failure behavior

If all search rows are rejected, the accepted result set is empty. Existing
application and bounded-live paths continue to produce `evidence_missing` when
no other source Evidence exists. No new public error or diagnostic receipt is
introduced.

## Authority And Compatibility

- The application database remains Evidence authority.
- Canonical artifact citation finalization remains application-owned.
- Evidence schema, verification, review, result, and delivery contracts do not
  change.
- The public API, database schema, migrations, provider declaration, model and
  tool budgets, dependencies, CI, and `VERSION` do not change.
- Search output and model text remain untrusted inputs.

## Verification

Verification covers the pure URL matrix, copied Tavily filtering, exact
source-authority gating, nested-stream ordering and deduplication, declared
fixture compatibility, the producer/consumer/receipt implication, runtime-
shaped accepted and all-invalid proofs, provider-free deterministic output,
and the required Docker authority lane.

## Non-Claims

This design does not claim source truth, independent verification, research
quality, provider quality, successful live observation, production readiness,
business acceptance, billing accuracy, or exactly-once execution.
