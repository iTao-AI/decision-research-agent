# Strict Exact-Source Citation Profile v1

**Status:** Approved public-neutral design source for mechanical landing and implementation planning.

## Summary

DRA already persists current-run Evidence independently from the canonical report and recomputes citation state by exact admitted-URL presence in that report. The generic profile deliberately treats zero cited Evidence as a warning, and canonical generic completion requires a non-empty report rather than a citation guarantee. Those semantics remain valid and backward compatible.

This design adds one opt-in strict profile for applications that require at least one current-run exact source citation before delivery can become ready. It reuses the generic research graph, tools, budgets, Evidence admission, persistence, artifact model, result resolver, and durable failure taxonomy. It changes only the application-owned finalization policy for runs created with the new profile.

If a non-fallback canonical report already contains an exact admitted URL from current-run source Evidence, finalization succeeds without an extra model call. Otherwise the application performs at most one bounded, same-run semantic correction through the run's configured LangChain chat model. The correction selects source-to-report placements; the application validates the selection, inserts the authoritative exact Markdown links, recomputes citations, and either completes or fails closed.

This is an opt-in delivery-integrity profile. It is not a change to generic behavior, a deterministic source dump, a citation-quality score, an EvalOps platform, or a claim that every statement is cited.

## Audited baseline

The design is bound to fresh live review of:

- `main == origin/main == 6a3020863fbaaf9d218420b7981150a5736b7fb8` at design approval;
- `deepagents==0.6.11`;
- `langchain==1.3.10`;
- `langchain-core==1.4.8`;
- `langgraph==1.2.6`;
- `langgraph-checkpoint==4.1.1`;
- the existing generic and talent profile registry;
- application-owned run creation, idempotency, dispatch fencing, execution, Evidence persistence, citation recomputation, artifact finalization, status projection, and result resolution;
- the existing durable `finalization/run_finalization_failed`, timeout, and cancellation semantics;
- the immutable v0.1.6 downstream consumer contract and producer identity; and
- the existing provider-free Backend CI lane.

Implementation must fresh-check the pinned package source/tests, the project's locked adapters, and current official documentation. The actual pinned versions and live application code remain the version-specific implementation authority.

## Product decision

Add exactly one registered profile:

```text
profile_id       = generic-strict-citation
profile_version  = 1
proof_schema     = dra.strict-citation-profile.v1
```

The profile is selected through the existing top-level `profile_id` request field and participates in the existing idempotency identity. It must not add a scope flag, request field, database column, migration, graph topology, tool, skill, or public consumer-contract revision.

The profile reuses the generic research runtime. A shared generic-family classification may be introduced where the current implementation incorrectly assumes that only the literal `generic` profile uses generic observation, finalization, or result-resolution behavior. This classification is application policy; it must not reinterpret the talent profile.

## Goals

The implementation must provide:

1. an explicit opt-in profile whose ready delivery proves at least one current-run exact admitted source URL is present in a non-fallback canonical report;
2. a zero-extra-call fast path when the initial report already satisfies that invariant;
3. at most one bounded same-run correction when the invariant is initially false;
4. deterministic application validation, insertion, citation recomputation, terminal state, and failure classification;
5. generic backward compatibility and no change to the v0.1.6 immutable consumer boundary;
6. provider-free TDD and CI proof across the real application lifecycle; and
7. documentation that makes opt-in semantics, coupling, non-claims, and release boundaries explicit.

## Non-goals

The implementation does not:

- change the generic profile's warning-only zero-citation behavior;
- relax any downstream exact-public-HTTPS source gate;
- append a source selected solely by application order or ranking;
- claim semantic support for every report statement;
- require all Evidence rows to be cited;
- guarantee citation correctness, completeness, source quality, or entailment;
- invoke a second correction or retry a failed correction;
- add a provider-backed CI test or require credentials in CI;
- introduce hosted tracing, a new evaluator platform, candidate promotion, or human review workflow;
- modify an existing release, tag, immutable producer identity, or downstream pinned artifact; or
- automatically require a new Release.

## Authority model

```text
configured run profile
        |
        v
shared generic research runtime
        |
        +--> canonical report candidate
        |
        +--> independently persisted current-run Evidence
                         |
                         v
application-owned exact-URL recomputation
        |
        +--> invariant satisfied --------> fenced ready finalization
        |
        +--> invariant unsatisfied
                         |
                         v
one bounded semantic placement call
                         |
                         v
application validates IDs and inserts authoritative links
                         |
                         v
application-owned exact-URL recomputation
        |
        +--> invariant satisfied --------> fenced ready finalization
        |
        +--> invariant unsatisfied ------> durable failed finalization
```

Authority remains separated as follows:

| Concern | Authority | Not authority |
| --- | --- | --- |
| Profile selection and version | application profile registry and persisted run identity | prompt wording, consumer convention |
| Run and terminal outcome | application DB and fenced runtime services | model narrative, graph state, trace |
| Source admission and identity | application Evidence persistence and source-admission policy | model-emitted URL or source claim |
| Semantic source placement | one bounded model selection over application-issued opaque IDs | application source order, deterministic appendix |
| Exact URL bytes and Markdown insertion | application-owned validated Evidence URL and renderer | model-generated URL text |
| Citation state | application recomputation from finalized artifact bytes | model assertion, correction response |
| Delivery readiness | strict profile invariant plus existing fenced finalization | warning count, downstream optimism |
| Consumer acceptance | consumer-owned policy applied to a newly pinned immutable producer identity | mutable main, profile name alone |

Persisted application state outranks model output, trajectory, checkpoint, trace, prompt, and Markdown narrative. The model can propose only a bounded placement mapping. It cannot create source identity, admit a URL, mark citations, choose terminal status, or bypass finalization.

## Strict success invariant

A `generic-strict-citation@1` run may finalize as `completed / not_required / ready` only when all of the following are true:

1. the generic execution outcome is otherwise eligible for canonical non-fallback delivery;
2. the canonical report exists, is non-empty, and satisfies existing artifact bounds;
3. at least one source Evidence row belongs to the same run and passed the existing source-admission rules;
4. the final canonical report contains the exact admitted URL bytes of at least one such current-run Evidence row; and
5. citation state is recomputed by the application from the final artifact bytes after any correction.

The profile makes no stronger claim. In particular, ready does not mean that every claim is cited or that the cited source entails the surrounding statement.

If the initial canonical report already satisfies the invariant, correction is not invoked. That zero-call branch is a required behavior and a provider-free test case.

Fallback output is never upgraded into canonical strict success merely by inserting a URL. Existing fallback semantics remain unchanged and fail or resolve according to current generic rules before the strict-ready invariant can be claimed.

## Correction trigger and preconditions

Correction is eligible only when:

- the run profile is exactly `generic-strict-citation@1`;
- the initial report is a non-fallback canonical candidate;
- the initial application recomputation finds zero cited current-run Evidence rows;
- at least one current-run admitted source Evidence row is available;
- the run still owns its dispatch/finalization fence;
- the shared run deadline has not expired; and
- cancellation has not won.

If no admitted current-run source Evidence exists, there is nothing valid to place. The application must not invoke correction and must fail through the strict finalization path.

Correction is part of the same run and the same finalization attempt. It does not create a child run, candidate, review item, promotion, second dispatch, or independent delivery artifact.

## Bounded correction contract

### Inputs

The application constructs a bounded correction packet from the canonical report candidate and current-run admitted source Evidence.

Report placement targets:

- at most 128 targets;
- each target is a stable application-issued opaque `target_id` plus at most 512 UTF-8 bytes of report text;
- targets are derived deterministically from eligible non-empty prose blocks in canonical report order;
- code fences, existing link destinations, raw HTML, and other unsafe insertion regions are not eligible targets; and
- target extraction must not change report bytes.

Evidence candidates:

- at most 100 current-run admitted source rows;
- each candidate exposes a stable application-issued opaque `source_id`, the authoritative exact admitted URL, and at most 512 UTF-8 bytes of bounded untrusted snippet/context;
- no provider diagnostic, host path, credential, private audit field, or unrelated Evidence body may enter the packet; and
- source order is deterministic but does not authorize the application to choose a source on the model's behalf.

Packet limits:

- serialized correction input is at most 512 KiB;
- unknown or excessive fields fail closed before invocation;
- Evidence snippets and report text remain untrusted data and are clearly delimited as data, never instructions; and
- all application-issued IDs are unique within the packet.

If the report or candidate Evidence cannot be represented within the declared limits while retaining at least one eligible target and source, correction is not invoked and finalization fails closed.

### Invocation

The application performs exactly one direct asynchronous invocation of the run's configured LangChain chat model.

The invocation must:

- reuse the already configured provider/model boundary for the run;
- use the shared remaining run deadline and cancellation authority;
- avoid DeepAgents orchestration, subagents, tools, search, skills, filesystem, virtual filesystem, checkpoints, and new graph execution;
- perform no internal application retry; and
- return only a bounded selection response.

A direct chat-model call is intentionally used because the task is a single constrained semantic mapping, not autonomous research. Re-entering the DeepAgents graph would enlarge authority, tool, context, and failure surfaces without adding a justified capability.

### Output

The model response is parsed as strict JSON with exactly one top-level field:

```json
{
  "placements": [
    {"target_id": "t1", "source_id": "s1"}
  ]
}
```

Rules:

- `placements` contains between 1 and the application-declared maximum number of items;
- every item contains exactly one issued `target_id` and one issued `source_id`;
- unknown fields, duplicate target IDs, duplicate pairs, unknown IDs, malformed JSON, non-string IDs, empty output, excessive count, or excessive bytes fail closed;
- the response contains no trusted URL, Markdown, report replacement, explanation, score, or terminal instruction; and
- parser behavior is deterministic and provider-independent.

Using a provider's optional structured-output feature is allowed only if the pinned adapter proves identical fail-closed semantics without adding a new compatibility dependency. The application validator remains authoritative in all cases.

### Application-owned insertion

After validation, the application inserts a canonical Markdown source link at each selected eligible target using the exact admitted URL associated with the selected `source_id`.

The renderer must:

- derive URL bytes only from persisted admitted Evidence;
- escape or encode link label text through one deterministic project-owned rule;
- preserve all report bytes except the declared insertions;
- apply placements in canonical target order rather than response order;
- reject a placement if the target is no longer byte-identical to the extraction basis;
- enforce existing artifact byte limits after insertion; and
- never fall back to an application-selected source or append a generic source list.

The application then reruns the existing exact-URL citation recomputation over the corrected artifact. The model response itself is not a citation result.

## Terminal behavior and failure taxonomy

The profile gets one correction opportunity. There is no second semantic call and no prompt-only retry.

After correction:

- if the strict success invariant holds, the application persists the corrected canonical artifact, recomputed citation states, and existing terminal ready projection atomically through the current fence;
- if the invariant still does not hold, validation fails, insertion fails, bounds fail, the model invocation fails, no eligible target/source exists, or correction otherwise cannot produce a valid artifact, the run finalizes as `failed / not_required / failed` with the existing bounded cause `finalization/run_finalization_failed`;
- if the shared run deadline expires, existing timeout classification wins;
- if cancellation wins, existing cancellation classification wins; and
- stale or losing writers remain no-ops under existing fencing rules.

Strict finalization failure must retain already persisted current-run Evidence and the bounded public-safe failure receipt. It must not persist or expose a ready artifact, partial corrected artifact, raw model response, provider diagnostic, prompt, snippet packet, exception body, or private path.

The design deliberately reuses the existing stable public failure taxonomy. It does not introduce a citation-specific public error code whose details could become a new consumer contract. Internal logs may identify the strict finalization step only within existing privacy and bounded-diagnostic rules.

## Profile, idempotency, and producer identity

The existing top-level run profile identity is the only feature-selection surface. The profile/version must participate in the same idempotency basis and persisted run identity exactly as existing registered profiles do.

The producer identity for a strict result is the immutable tuple:

```text
repository + release/tag-or-commit + profile_id + profile_version + proof_schema
```

A downstream application must pin and validate a new immutable producer identity before accepting strict-profile output. It must not infer this capability from mutable `main`, from `VERSION=0.1.6`, or from the profile name alone.

A DRA repository version change does not automatically force a downstream upgrade. A consumer upgrades only when it intentionally re-pins a producer identity whose contract it needs. Conversely, DRA does not edit, re-pin, or weaken a downstream consumer as part of this change.

## Compatibility

### Generic profile

The literal `generic` profile keeps all existing behavior:

- zero exact citations remain warning-only;
- a canonical non-empty report may still become ready;
- no correction call is made; and
- existing API, result, proof, and v0.1.6 consumer tests remain unchanged.

### Talent profile

Talent review, checkpoint, publication, and result semantics are unchanged. The generic-family helper must not cause talent runs to enter generic strict finalization.

### Public API and storage

The change adds a registry value accepted by the existing `profile_id` field. It adds no new top-level request field, database schema, migration, status enum, artifact kind, failure-cause enum, or downstream contract field.

Unknown profiles and unsupported versions continue to fail through the existing closed validation behavior.

## Framework reuse decision

The design reuses:

- the existing DRA profile registry and run identity;
- the existing generic DeepAgents research graph;
- the configured LangChain chat-model adapter for one direct `ainvoke`-style correction;
- existing Evidence admission and persistence;
- existing exact-URL citation recomputation;
- existing fenced terminal finalization;
- existing durable failure taxonomy; and
- existing provider-free Harness/fake adapter patterns.

The design rejects:

- a second DeepAgents graph or subagent for correction, because it would expose tools and autonomous control not required by the bounded mapping;
- a LangGraph checkpoint or trace as application authority, because persisted DRA state remains authoritative;
- an application-selected deterministic source appendix, because ordering is not semantic support;
- a scope flag, because this is a versioned product policy rather than free-form run metadata; and
- a new database column or public failure code, because the existing profile identity and failure taxonomy are sufficient.

Implementation must verify the exact invocation and message APIs against pinned source/tests and current official documentation. Framework convenience must not weaken application validation or authority separation.

## TDD and provider-free proof

Implementation is RED-first. Tests must prove failure before production changes and must cover the real create-to-resolve lifecycle rather than only a helper.

Required unit coverage includes:

1. profile registration, version, and generic-family classification;
2. existing request validation and idempotency separation between `generic` and `generic-strict-citation`;
3. deterministic target extraction and exclusion of unsafe regions;
4. correction packet count, field, depth, and byte bounds;
5. untrusted-data delimiting and absence of forbidden private/provider fields;
6. strict JSON response parsing and rejection of unknown, duplicate, malformed, or excessive values;
7. authoritative source-ID lookup and exact URL insertion;
8. deterministic placement order and stale-target rejection;
9. post-insertion artifact-bound enforcement;
10. zero-call success when an initial exact admitted URL is already present;
11. no-call failure when no admitted current-run source exists;
12. exactly one direct correction call on the eligible zero-citation path;
13. no second call after malformed output or unsuccessful recomputation;
14. generic and talent non-regression; and
15. timeout, cancellation, and stale-fence precedence.

Required integration proof traverses:

```text
create
  -> persisted profile identity and idempotency
  -> dispatch
  -> shared generic execution
  -> independently persisted Evidence
  -> initial exact-URL recomputation
  -> zero-call success OR one bounded correction
  -> application validation and insertion
  -> post-correction recomputation
  -> fenced persistence
  -> status reread
  -> result resolver
```

The provider-free fake must expose an explicit call count and scripted bounded responses. It must not make network, credential, provider, Docker, or hosted-service calls.

At minimum, integration cases must prove:

- strict initial success with zero correction calls;
- strict correction success with exactly one call and exact persisted admitted URL bytes in the resolved canonical artifact;
- malformed/unknown-ID correction failure with exactly one call, retained Evidence, no ready artifact, and `finalization/run_finalization_failed`;
- valid-looking correction whose recomputation remains zero cited, with the same fail-closed terminal result and no second call;
- no admitted source Evidence, with zero calls and fail-closed finalization;
- generic zero-citation ready behavior remains unchanged and makes zero correction calls;
- timeout and cancellation during correction use existing classifications; and
- status and result APIs remain internally consistent after both strict success and strict failure.

The existing immutable downstream consumer contract proof must remain green without reinterpretation. A separate public-safe fixture may prove the new strict profile, but it must not mutate or silently upgrade the v0.1.6 fixture.

## Observability and privacy

The implementation may expose only bounded public-safe state already allowed by current status and failure contracts. It must not expose correction prompts, report target text, Evidence snippets, model response bodies, provider diagnostics, exception strings, host paths, credentials, or raw internal traces.

Logs and tests may use stable event or counter identities for:

- strict finalization entered;
- initial invariant satisfied;
- correction invoked once;
- correction validation failed;
- post-correction invariant satisfied; and
- strict finalization failed.

These signals are operational diagnostics, not new public API fields or business facts.

No hosted tracing dependency is required. Provider-free CI evidence is the acceptance authority for deterministic application behavior; any later live-provider exercise is separately governed and cannot replace it.

## Documentation

The implementation PR must update the public documentation needed to answer:

- how to opt into `generic-strict-citation@1` through the existing `profile_id` field;
- what ready proves and does not prove;
- why generic behavior remains unchanged;
- how the one-call correction and fail-closed terminal path work;
- how a consumer pins the immutable producer identity;
- why a DRA version change does not automatically require a consumer upgrade; and
- why Release is a separate decision.

Documentation must remain public-neutral. It must not name a private downstream project, career goal, private workspace, provider credential, local machine path, or private governance label.

## Release boundary

Landing and merging this capability do not automatically authorize or require a Release.

A Release should be proposed only when either:

1. a coherent bounded release pack exists, including implementation, provider-free proof, documentation, and a stable immutable producer identity suitable for intentional consumer pinning; or
2. a real consumer need requires a published artifact rather than a commit-pinned proof.

Until then, the capability may exist on main without being described as part of v0.1.6. Existing release notes, tag, version file, artifact, and consumer claims remain immutable.

## Alternatives rejected

### Prompt or query strengthening only

Rejected as the primary fix. It may increase citation likelihood but cannot establish application-owned deterministic delivery integrity and has already shown that more retrieval does not guarantee exact URL presence in the final report.

### Downstream gate relaxation

Rejected. A strict consumer should not accept zero cited exact sources merely because the producer completed generic delivery.

### Deterministic source appendix

Rejected. Appending the first or highest-ranked admitted source would prove URL presence but not a semantic relationship to report content. The application must not manufacture that relationship from ordering alone.

### Change generic completion globally

Rejected. It would break the established generic contract and force unrelated consumers into a stronger policy they did not request.

### New request flag or database migration

Rejected. The existing versioned profile identity is the correct bounded policy surface.

### New citation-specific public failure code

Rejected. Existing `finalization/run_finalization_failed` is sufficient and avoids unnecessary consumer coupling.

## Acceptance criteria

The phase is acceptable only when:

- the new profile is explicit, versioned, and isolated from generic/talent semantics;
- the initial-success branch makes zero correction calls;
- the eligible correction branch makes exactly one direct bounded model call;
- the application, not the model, owns exact URL bytes, insertion, citation recomputation, and terminal state;
- unsuccessful strict finalization is `failed / not_required / failed` with the existing bounded failure cause and no ready artifact;
- already persisted Evidence survives strict finalization failure;
- provider-free tests traverse create, dispatch, execution, correction/finalization, persistence, status, and result resolution;
- generic, talent, v0.1.6, and immutable consumer proofs remain green without reinterpretation;
- public docs state opt-in semantics, non-claims, consumer pinning, and Release separation; and
- no provider, credential, Docker, hosted tracing, downstream mutation, version bump, tag, or Release is required for CI acceptance.

## Stop conditions

Stop and return to architecture authority rather than expanding scope if implementation evidence shows that:

- the existing profile identity cannot carry the policy without a migration or public API expansion;
- direct use of the configured chat model cannot share the current deadline, cancellation, or privacy boundary;
- exact application-owned insertion cannot preserve artifact and Markdown safety bounds;
- strict failure cannot retain Evidence while preventing ready artifact exposure under the existing fenced finalization transaction;
- generic/talent behavior would need reinterpretation;
- pinned framework behavior contradicts the direct-call contract; or
- provider-free lifecycle proof cannot reach the same production finalization and resolver path.

Do not work around a stop condition with a second model call, deterministic source dump, consumer gate relaxation, or hidden contract expansion.

## Non-claims

This design proves only a bounded application behavior for an opt-in profile:

- a ready strict artifact contains at least one exact URL admitted from current-run source Evidence;
- the semantic placement was selected once by the configured model from bounded application-issued IDs; and
- the application validated, inserted, recomputed, persisted, and resolved the result under existing authority and fencing.

It does not prove source truth, source quality, entailment, citation completeness, universal model compliance, production reliability across providers, hosted observability, business impact, or downstream adoption.
