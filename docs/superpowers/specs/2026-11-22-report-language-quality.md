# Report language and Chinese research quality

## Delivery contract

The console sends `scope.report_language` for new `generic` and
`generic-evidence-report` runs. Accepted values are `zh-CN` and `en`. This is
the language of the persisted report, determined when creating the intent.
The input questions remain caller-authored data. Changing the console language
later changes its controls. Repeating an intent sends the same key and scope.
A different language on the same key is a request mismatch.

When the key is omitted from the scope, legacy normalization, request hashes,
generation inputs, and report bytes remain stable. Explicit invalid values,
including null, fail validation before dispatch. The repository and existing
dispatch handoff carry the accepted scope through recovery. Scope and report
JSON retain their existing versioning. Other profiles keep their existing
scope contracts.

For generic output the agent writes the selected-language Markdown through the
normal result path. The fallback template follows the same language and can
include the bounded original last agent text. For evidence output the agent
authors statements, unresolved reasons, contradictions, and limitations in the
selected language. The application renders Markdown using the pinned profile
version and persisted language. English and omitted language retain the same
v1 formatter. The independent reader verifies identity, artifact hashes,
reference offsets and exact Markdown. Exact excerpts remain in the source
language. Roll out compatible readers before enabling writers.

## Evaluation and decision

Use four development cases covering Zotero sync, release asset download
counts, customer-service approval and retry, and a troubleshooting agent with
complete and reduced material. Prepare held-out all-day calendar and Talent
samples independently before candidate selection. Talent checks its separate
scope and evidence contract. Keep the English replay corpus as regression.

Use the existing provider-free binder and observation replay for a historical
execution-only citation failure. Keep zero, unique, and ambiguous match
replays separately attributable. With no delivered artifact the semantic
verdict remains unavailable. Capture hashes and explicit model, rubric and
method identities for blinded semantic grading. Report programmatic checks,
actual generation, model judgements, and replay separately.

Select a single candidate only after reproducing an attributable defect.
Compare on identical inputs, configuration and limits. Recommend adoption
only when the original defect improves, an independent source family supports
the improvement, and normal and held-out controls have no important
regressions. Preserve the baseline when evidence is insufficient.
