# Evidence Source Admission Closure Implementation Plan

Status: Approved

## Scope

Implement the approved producer URL admission and generic Evidence authority
closure without changing public errors, schemas, budgets, providers,
dependencies, CI, or release metadata.

## Task 1: Publishable URL Policy

RED:

- Add a focused unit matrix for canonical public HTTPS URLs and rejected
  schemes, identities, hosts, ports, IP literals, query/fragment values,
  malformed values, Unicode/control input, and size bounds.
- Add copy, order, all-invalid, and malformed-response tests for Tavily-shaped
  filtering.

GREEN:

- Add the small pure `agent/source_url_policy.py` module.
- Keep the policy network-free, fail closed, and non-rewriting.

Verification:

- Run the focused URL policy tests in the locked Python 3.11 environment.

## Task 2: Tavily Source Boundary

RED:

- Prove mixed provider-shaped rows currently reach the model and monitor.
- Prove an all-invalid response is not reduced to an empty accepted set.

GREEN:

- Filter the copied Tavily response immediately after provider return and
  before cache consumers, the model, and `monitor.report_end()`.
- Preserve accepted fields and deterministic order.

Verification:

- Run the URL policy and Tavily unit tests with no provider call or credential.

## Task 3: Generic Evidence Authority

RED:

- Prove outer task, file, database, knowledge-base, and arbitrary tool messages
  can currently create Evidence.
- Prove direct extraction currently admits URLs rejected by publication.
- Extend locked nested-stream coverage with invalid rows and distinct outer
  summaries.

GREEN:

- Admit generic stream Evidence only for the exact
  `network_search` / `internet_search` pair.
- Apply URL admission in `extract_evidence_entries()`.
- Remove the obsolete outer-task identity suppression and retain deterministic
  merge/deduplication for real source rows.
- Preserve `provided_aggregate` declared-fixture preload semantics.

Verification:

- Run research, run-result, locked nested harness, and declared-fixture tests.

## Task 4: Cross-Layer Implication

RED:

- Add a table-driven producer/downstream/receipt matrix for both known drift
  groups and stricter canonical producer cases.
- Prove the receipt does not yet reject every producer-rejected canonicality
  mutation.

GREEN:

- Reuse the pure predicate in `EvidenceReceipt`.
- Keep the downstream consumer validator independent.
- Add runtime-shaped mixed and all-invalid provider-free proofs.

Verification:

- Run downstream, bounded-live contracts, proof, and implication tests.

## Task 5: Documentation And Completion

RED:

- Add executable documentation and Unreleased contracts before updating text.

GREEN:

- Update the current state-machine and bounded-live reference contracts.
- Record the change in `CHANGELOG.md` Unreleased.
- Keep this design and plan concise and public-neutral.

Final verification:

- Run focused and complete affected provider-free matrices.
- Run the deterministic bounded-live check twice and compare exact bytes with
  empty stderr.
- Run canonical identity, presentation, docs, and release contracts.
- Run the clean-HEAD required Docker authority lane after capacity and
  ownership preflight, then remove only task-owned resources.
- Run `git diff --check` plus scope, private-marker, credential,
  unfinished-marker, and live-evidence absence scans.

No `observe-live`, provider, model, search, credential, push, PR, merge,
release, deployment, or protected-worktree action is part of this plan.
