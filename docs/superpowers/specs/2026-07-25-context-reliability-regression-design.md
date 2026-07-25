# Context Reliability Paired Pytest Regression Design

**Status:** Approved public-neutral design source for mechanical landing and implementation planning.

## Summary

Decision Research Agent delegates context-window mechanics to DeepAgents while keeping ResearchRun, Evidence, citations, artifacts, finalization, review, result resolution, and delivery under application authority.

The repository has context-pressure evidence, but no retained observation currently proves that native summarization caused an application invariant failure. This design therefore adds an evaluation-only regression pack rather than a custom compactor or runtime hardening.

For one fixed synthetic generic scenario, the pack runs the same deterministic task through:

1. a control lane in which native summarization does not trigger; and
2. a forced lane in which the locked DeepAgents native coordinator summarizer does trigger.

Trajectory differences are allowed. The regression passes only when the enumerated application-owned persisted projections remain equivalent.

## Audited Baseline

This design was finalized against:

- DRA v0.1.6 at commit `7d43324b469cb5e445c2e8be83af3be4d841cf1c`;
- `deepagents==0.6.11`;
- `langchain==1.3.10`;
- `langchain-core==1.4.8`;
- `langgraph==1.2.6`;
- `langgraph-checkpoint==4.1.1`;
- the existing generic DeepAgents harness;
- application-owned run, Evidence, artifact, finalization, and result-resolution paths;
- the existing non-Docker `Backend Tests` pytest collection.

A previous high-token observation is context-pressure evidence only. It does not establish that native summarization ran or that an application invariant failed.

## Decision

Add a provider-free paired pytest regression pack answering one bounded question:

> For one fixed deterministic generic research task, does forcing the locked DeepAgents native coordinator summarizer change the application-owned persisted outcome compared with a non-triggered control run?

This is an extension of the existing Agent evaluation namespace. It is not a second evaluation platform and does not introduce a new runtime policy.

## Authority Boundaries

| Dimension | Owner | Regression assertion |
|---|---|---|
| Input query | DRA run persistence | Same SHA-256 after excluding run-local identity |
| Nested search Evidence | DRA Evidence ledger | Same normalized semantic set and valid run-scoped IDs |
| Evidence fingerprints | DRA Evidence ledger | Same fingerprints |
| Citation states | DRA finalization | Same persisted states |
| Verification states | DRA Evidence ledger | Same persisted states |
| Canonical result artifact | DRA result service | Same artifact projection and content hash |
| Terminal state | DRA run state machine | Same execution, review, and delivery tuple |
| Result resolution | `resolve_run_result()` | Same normalized success or error projection |
| Summary trigger and effective messages | DeepAgents/model boundary | Characterization only |
| Exact sequential search deduplication | DRA search cache | Existing exact `query + kwargs` behavior only |
| Required-domain satisfaction | Bounded-live evaluation policy | Outside generic runtime equivalence |
| TODO and correction state | Framework/private trajectory | Optional compatibility observation, not application outcome |
| Stop-condition enforcement | No generic server-owned policy | Not observed |
| Provider summary quality | Provider/model behavior | Not observed |

Framework runtime state, summaries, traces, and checkpoints do not become application authority.

## Paired Scenario

Both lanes use unique `run_id` and `thread_id` values and the same deterministic query, tool arguments, public synthetic source, and canonical report content.

### Control lane

A test-only model profile keeps the synthetic task below the native summarization threshold. No summarization call may be observed.

### Forced lane

A small test-only model profile crosses the native threshold without replacing or patching the framework middleware.

The coordinator delegates to the deterministic `network_search` subagent. Its `internet_search` tool returns bounded `example.com` data. The researcher returns a large coordinator-facing `task` result that omits the source URL but is sufficient to trigger coordinator summarization.

The required observable ordering is:

```text
nested internet_search Evidence event
  -> large coordinator-facing task result
  -> summary call with lc_source=summarization
  -> coordinator agent-model call receiving the summary message
  -> canonical write_file
```

The compiled researcher is a plain LangChain agent and does not receive the DeepAgents coordinator summarizer. A large researcher ToolMessage alone is therefore not proof that the required summarization path ran.

## Real Application Traversal

Each lane must traverse:

```text
create_run
  -> claim/start dispatch fence
  -> _run_dispatched_with_persistence
  -> ResearchExecutionService
  -> artifact and citation finalization
  -> finalize_run_transaction
  -> get_run
  -> resolve_run_result
  -> normalized application projection
```

The integration test may replace only `api.server.run_deep_agent` with a test-owned async adapter that invokes a real `ResearchExecutionService`. Persistence, dispatch fencing, finalization, result resolution, and search-cache cleanup remain real.

Each lane independently asserts:

- `state_version == 2`;
- the initial segment is `completed`;
- dispatch status is `started`;
- `failure_cause is None`;
- exactly one `research-report.md` artifact exists.

## Application Equivalence Projection

Add pure internal helpers under the existing Agent evaluation namespace:

- `project_context_reliability_outcome()`;
- `compare_context_reliability_outcomes()`.

The projection validates its input and produces the following deterministic, public-safe shape:

```text
query_sha256

evidence[] sorted by evidence_fingerprint:
  evidence_fingerprint
  source_identity_sha256
  snippet_sha256
  query_text_sha256
  subagent_name
  tool_name

citation_states[] sorted by evidence_fingerprint:
  evidence_fingerprint
  citation_status

verification_states[] sorted by evidence_fingerprint:
  evidence_fingerprint
  verification_status

artifacts[] sorted by artifact_id:
  artifact_id
  kind
  media_type
  content_hash

terminal:
  execution_status
  review_status
  delivery_status

resolver success:
  execution_status
  delivery_status
  selected artifact_id
  selected artifact kind
  selected artifact media_type
  selected artifact content_hash

resolver error:
  status_code
  code
  retryable
```

Every Evidence row must satisfy:

```text
evidence_id == "ev_" + run_id + "_" + evidence_fingerprint
```

Run IDs, thread IDs, timestamps, raw queries, snippets, prompts, and local paths are excluded from the emitted comparison projection. Sensitive text is represented only by deterministic hashes.

Malformed input fails closed with:

```text
context.projection_invalid
```

Validation details and raw field values are not returned.

## Comparison Findings

Stable finding codes are:

- `context.query_changed`
- `context.evidence_changed`
- `context.citation_state_changed`
- `context.verification_state_changed`
- `context.artifact_changed`
- `context.terminal_state_changed`
- `context.result_resolution_changed`

An empty ordered finding list is the only passing equivalence result.

These codes describe paired application-projection differences. Framework activation, persistence traversal, Evidence capture, and deduplication failures remain named pytest assertions rather than new public error codes.

## Negative Controls

Unit tests mutate one normalized dimension at a time and prove the corresponding finding is emitted:

- query hash;
- Evidence fingerprint;
- citation status;
- verification status;
- canonical artifact content hash;
- delivery status;
- resolved-result artifact hash.

Parameterized cases use stable descriptive IDs. Multiple mutations must produce stable ordered findings.

A dimension may not be removed or ignored to make a regression pass.

## Framework Compatibility Characterization

A structural test assembles the real `build_generic_harness()` path and verifies:

- exactly one native `SummarizationMiddleware` is installed in the coordinator stack;
- the production `FallbackChatModel` has no aggregate model profile and follows the locked no-profile fallback path;
- a test-only profiled model can force native summarization without changing production configuration or replacing middleware;
- the control lane records no summary call;
- the forced lane records a native summary call and a subsequent coordinator agent-model call.

Locked cutoff and retention values are compatibility facts, not public reliability promises. The test does not assert that arbitrary provider-generated summary prose preserves prompts or markers.

## Duplicate-Process Observation

After the forced-summary point, two sequential searches with exactly the same query and keyword arguments must invoke the underlying fake search once.

The cache is scoped by the active run ID. Each lane uses unique run and thread identities. `ResearchExecutionService` must clear the run-scoped cache on return.

This does not claim:

- concurrent duplicate suppression;
- semantic-query deduplication;
- duplicate delegation prevention;
- global cache behavior.

## Implementation Scope

The implementation following this design is limited to seven files:

```text
scripts/agent_evaluation_context.py
tests/unit/test_agent_evaluation_context.py
tests/unit/test_deepagents_harness.py
tests/integration/test_context_reliability_regression.py
tests/unit/test_documentation_contracts.py
docs/reference/context-reliability-regression.md
docs/README.md
```

The design file itself is the approved planning artifact and is not counted as implementation code.

No implementation change is planned for:

- production files under `agent/`, `api/`, or `tools/`;
- Agent evaluation scenario manifests or canonical reports;
- `.github/workflows/ci.yml`;
- top-level `README.md`, `README_CN.md`, or `CHANGELOG.md`;
- API, database, migration, dependency, release, or consumer contracts.

If a production-file change appears necessary, implementation stops and requests architecture review.

## Test Structure

Tests must be behavior-named and independently runnable. At minimum they isolate:

1. native middleware and profile characterization;
2. control-versus-forced summary-trigger observation;
3. paired persisted-outcome equivalence;
4. nested Evidence preservation;
5. post-summary exact sequential deduplication and cache cleanup.

The documentation contract locks the final stable node names and focused commands.

## Developer Experience

The public reference page is titled **Context Reliability Pytest Regression Pack** and states:

- this is a pytest-collected regression pack, not a standalone gate;
- there is no CLI or `build`, `check`, `accept`, or `regenerate` operation;
- there is no committed output artifact or baseline;
- there is no independent CI job or required-check name;
- pytest assertions are the executable authority;
- the existing `Backend Tests` generic pytest command collects the pack.

The page provides:

- a Python 3.11 setup pointer to `CONTRIBUTING.md`;
- the fast unit command;
- the complete focused pack;
- a diagnostic rerun;
- CI-parity and public-document verification;
- the passing semantics;
- three-part failure diagnosis;
- symbol-level code navigation;
- safe-update and stop rules.

## Verification Contract

```bash
# Fast projection/evaluator check
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_agent_evaluation_context.py

# Complete focused pack
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py

# Diagnostic rerun
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -vv -x tests/integration/test_context_reliability_regression.py

# CI parity and public-document verification
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
python scripts/final_presentation_audit.py --root .
git diff --check
```

Passing means exit code zero with every selected test passing. Documentation must not promise a fixed test count or elapsed time.

## Privacy And Safety

- Fixtures use deterministic public `example.com` URLs and synthetic text.
- No credential, provider, network, Docker, live user data, raw prompt, raw Evidence content, host path, database path, or provider error is retained.
- Oversized synthetic payloads remain bounded below existing test and artifact limits.
- Malformed persistence or resolver projections fail closed.
- Summary quality and framework-private internals are not serialized as public evidence.

## Safe Update Rules

- If the locked DeepAgents version changes, adjust only the test profile or bounded payload required to preserve one non-triggered and one forced lane.
- If application authority gains a new projected field, add the projection field, negative control, and finding code together.
- Any paired application drift must be investigated as a RED result.
- Do not regenerate a baseline, delete an asserted dimension, loosen equality, or change production behavior merely to make the pack pass.

## Allowed Claim

> For one fixed synthetic generic scenario under `deepagents==0.6.11`, the provider-free paired pytest regression observes native coordinator summarization only in the forced lane and checks that the enumerated application-owned persisted projections remain equivalent to the control lane.

## Non-Claims

This design does not prove:

- live-provider summary quality;
- arbitrary-task or unlimited-context reliability;
- preservation of every URL, TODO, stop condition, or semantic detail;
- generic required-domain enforcement;
- concurrent or semantic duplicate-search prevention;
- production scale, latency, business impact, or user adoption;
- any change to DRA v0.1.6 or an existing consumer contract.

## Stop Conditions

Stop and request architecture review if:

- the forced lane changes an application-owned projection;
- native summarization cannot be triggered through the locked framework without patching or replacing it;
- production middleware, API, database, dependency, CI, release, or consumer changes appear necessary;
- exact sequential deduplication fails outside its existing bounded contract;
- passing would require hiding drift, deleting a dimension, accepting a baseline, or exposing private content;
- the pack cannot remain deterministic, provider-free, network-free, Docker-free, and bounded in existing CI.

## Approval Boundary

Approval of this design permits implementation planning only after the landed spec diff receives authority review.

It does not authorize implementation, push, PR, merge, tag, release, provider-backed execution, or deployment.
