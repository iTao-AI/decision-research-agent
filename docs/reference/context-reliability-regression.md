# Context Reliability Pytest Regression Pack

This is a pytest-collected regression pack, not a standalone gate. It has no
CLI, no `build` operation, no `check` operation, no `accept` operation, and no
`regenerate` operation. It creates no committed output artifact or baseline and
has no independent CI job or required-check name. Pytest assertions are the
executable authority, and the existing `Backend Tests` generic pytest command
collects the pack.

## Setup

Use the Python 3.11 contributor environment documented in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). The pack is provider-free,
credential-free, network-free, and Docker-free.

## Commands

Fast projection/evaluator check:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_agent_evaluation_context.py
```

Complete focused pack:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

Diagnostic rerun:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -vv -x tests/integration/test_context_reliability_regression.py
```

CI parity and public-document verification:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
python scripts/final_presentation_audit.py --root .
git diff --check
```

## Passing Semantics

Passing means exit code zero with every selected test passing. The control lane
records no native summary call. Native summarization is observed only in the
forced lane, where `lc_source=summarization` is followed by a coordinator model
call consuming the native summary and, later, canonical `write_file`. The
paired comparison returns an empty ordered finding list for the enumerated
application-owned persisted projections.

## Failure Diagnosis

| Symptom | Owner | First exact symbol or file to inspect | Prohibited false fix |
|---|---|---|---|
| An ordered `context.*_changed` finding | Application projection evaluator | `scripts/agent_evaluation_context.py::compare_context_reliability_outcomes` | Do not delete a projected dimension or loosen equality. |
| `context.projection_invalid` | Projection input validation | `scripts/agent_evaluation_context.py::project_context_reliability_outcome` | Do not accept malformed input, expose raw values, or create or update a baseline. |
| A named pytest assertion failure for activation, traversal, Evidence, deduplication, or cleanup | Framework or application traversal assertion | The failing stable node in `tests/unit/test_deepagents_harness.py` or `tests/integration/test_context_reliability_regression.py` | Do not patch or replace native middleware. Do not change production behavior to make the pack pass. |

Malformed projections expose no raw field value. The three diagnosis classes
remain distinct: application projection drift belongs to the evaluator,
projection rejection belongs to input validation, and named assertion failures
belong to the exact framework or application traversal boundary named by
pytest.

## Code Navigation

- `scripts/agent_evaluation_context.py::project_context_reliability_outcome`
  validates and hashes persisted state.
- `scripts/agent_evaluation_context.py::compare_context_reliability_outcomes`
  emits stable ordered findings.
- `agent/deepagents_harness.py::build_generic_harness` installs the native
  coordinator middleware.
- `api/research_execution_service.py::ResearchExecutionService.execute` owns
  runtime context, Evidence freeze, and run-cache cleanup.
- `api/server.py::_run_dispatched_with_persistence` crosses the start fence.
- `api/run_repository.py::finalize_run_transaction` performs fenced atomic
  finalization.
- `api/run_repository.py::get_run` reads the application-owned persisted run.
- `api/run_result_service.py::resolve_run_result` resolves the selected result.
- `tools/tavily_tools.py::search_with_dedup` owns exact sequential search
  deduplication.
- `tools/tavily_tools.py::clear_search_cache` clears the run-scoped cache.
- `tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary`
  characterizes the locked middleware/profile boundary.
- `tests/integration/test_context_reliability_regression.py::test_control_and_forced_lanes_observe_native_summary_only_when_forced`
  locks paired summary activation.
- `tests/integration/test_context_reliability_regression.py::test_paired_persisted_application_outcomes_remain_equivalent`
  locks persisted application equivalence.
- `tests/integration/test_context_reliability_regression.py::test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache`
  locks nested Evidence, post-summary exact sequential deduplication, and
  cleanup.

## Safe Updates And Stop Rules

- If the locked DeepAgents version changes, adjust only the test profile or
  bounded payload required to preserve one non-triggered and one forced lane.
- If application authority gains a new projected field, add the projection
  field, negative control, and finding code together.
- Investigate any paired application drift as a RED result.
- Do not delete a projected dimension or loosen equality.
- Do not create or update a baseline.
- Do not patch or replace native middleware.
- Do not change production behavior to make the pack pass.
- Stop and request architecture review if the forced lane changes an
  application-owned projection.
- Stop and request architecture review if native summarization cannot be
  triggered through the locked framework without patching or replacing it.
- Stop and request architecture review if production middleware, API,
  database, dependency, CI, release, or consumer changes appear necessary.
- Stop and request architecture review if exact sequential deduplication fails
  outside its existing bounded contract.
- Stop and request architecture review if passing would require hiding drift,
  deleting a dimension, accepting a baseline, or exposing private content.
- Stop and request architecture review if the pack cannot remain
  deterministic, provider-free, network-free, Docker-free, and bounded in
  existing CI.

## Scope And Non-Claims

For one fixed synthetic generic scenario under `deepagents==0.6.11`, the
provider-free paired pytest regression observes native coordinator
summarization only in the forced lane and checks that the enumerated
application-owned persisted projections remain equivalent to the control lane.

This pack does not prove:

- live-provider summary quality;
- arbitrary-task or unlimited-context reliability;
- preservation of every URL, task-list entry, stop condition, or semantic
  detail;
- generic required-domain enforcement;
- concurrent or semantic duplicate-search prevention;
- production scale, latency, business impact, or user adoption;
- any change to DRA v0.1.6 or an existing consumer contract.
