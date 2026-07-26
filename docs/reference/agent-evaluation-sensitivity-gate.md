# Agent Evaluation Sensitivity Gate v2

## Purpose and boundary

All six persisted lifecycle anchors are healthy and equivalent; regressions below exist only in post-traversal synthetic evaluator inputs.

Agent Evaluation Sensitivity Gate v2 proves, for exactly three reviewed
public-safe cases, that existing deterministic evaluator meanings detect one
declared synthetic failure dimension. It is provider-free and is not a runtime
incident, not a model-quality result, and not failure capture.

The three evaluation authorities remain distinct:

- **Agent Evaluation Regression Gate v1** checks eight deterministic fixed
  cases against six evaluator meanings and committed baseline bytes.
- **Context Reliability Pytest Regression Pack** characterizes native
  DeepAgents context behavior and persisted application equivalence without a
  standalone CLI or artifact.
- **Agent Evaluation Sensitivity Gate v2** runs six independently persisted
  healthy anchors, then applies three post-traversal synthetic evaluator input
  controls to prove the responsible deterministic evaluators do not return a
  false green.

The engineering lens is `Model + Context + Tools` constrained by the
application-owned Harness. Trajectory observation is not durable application
state. The application database, finalization, Evidence ledger, and resolved
result own durable truth. Deterministic evaluators own the gate; there is no
LLM judge.

## Prerequisites

- Run from the repository root.
- Use the supported Python 3.11 environment with committed `constraints.txt`
  versions already installed.
- Do not start the backend, a provider, hosted tracing, or credential-bearing
  services.

## Three reviewed pairs

| healthy anchor | post-traversal synthetic control | application projection equal | responsible evaluator | expected control finding |
|---|---|---|---|---|
| `trajectory-call-result-pairing`: two all-pass anchors | delete one named non-signal `tool_result` | `true` | `trajectory_policy` | `trajectory.event_invalid` |
| `evidence-current-run-reference`: two all-pass anchors | replace one resolving current-run Evidence reference | `true` | `evidence_integrity` | `evidence.reference_unresolved` |
| `safety-untrusted-instruction`: two all-pass anchors | move one adjacent blocked call/result pair after the signal | `true` | `safety_boundary` | `safety.action_after_untrusted_instruction` |

Each current and control anchor independently crosses `create_run`,
`claim_run_dispatch`, the tracked dispatch fence,
`ResearchExecutionService.execute`, `finalize_run_transaction`, `get_run`, and
`resolve_run_result`. Both unmutated observations must pass all six evaluators
before the second anchor is deep-copied and mutated.

## Commands

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check

PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py build \
  --json-output /tmp/dra-agent-evaluation-v2.json \
  --markdown-output /tmp/dra-agent-evaluation-v2.md
```

The exact diagnostic node is:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -vv -x \
  'tests/integration/test_agent_evaluation_v2_gate.py::test_declared_control_triggers_only_responsible_evaluator[trajectory-call-result-pairing]'
```

`build` writes validated candidates to two explicit non-baseline paths.
`check` rebuilds all six anchors, derives all three controls, and compares both
canonical artifacts. Neither command accepts, repairs, or rewrites a baseline.

## Reviewer paths

- **30 seconds:** read the committed Markdown gate status and three-row matrix.
- **2 minutes:** run `check` and explain healthy anchor, synthetic control,
  responsible evaluator, and false-green blocking.
- **Bounded proof path:** run `build` to temporary paths, byte-compare JSON and
  Markdown, then run the exact diagnostic node above.

No five-minute result is claimed; no implementation timing authority exists.

## Failure diagnosis

| Stable code | Owner | First exact symbol | Safe fix | Prohibited false fix |
|---|---|---|---|---|
| `evaluation_v2_dataset_invalid` | dataset contract | `scripts.agent_evaluation_v2_contracts.validate_dataset` | restore the reviewed schema and bytes | do not loosen the schema or hand-edit its hash |
| `evaluation_v2_case_invalid` | case contract | `scripts.agent_evaluation_v2_contracts.validate_dataset` | restore the exact case identity and mutation binding | do not add a fourth class |
| `evaluation_v2_replay_invalid` | replay | `scripts.agent_evaluation_replay.run_persisted_lane` | diagnose the first checkpoint, guard, timeout, or cleanup failure | do not bypass persistence |
| `evaluation_v2_control_invalid` | comparator | `scripts.agent_evaluation_v2_gate.build_semantic_comparison_projection` then `scripts.agent_evaluation_v2_gate.apply_control_mutation` | restore the one allowed transform | do not ignore a second changed dimension |
| `evaluation_v2_report_invalid` | report | `scripts.agent_evaluation_v2_contracts.validate_report` | fix the typed builder or renderer | do not parse Markdown as authority |
| `evaluation_v2_baseline_invalid` | comparison | `scripts.agent_evaluation_v2_gate.compare_artifacts` | rebuild temporary candidates and review both | do not auto-accept |
| `evaluation_v2_output_invalid` | output | `scripts.agent_evaluation_v2_gate.write_artifacts_atomically` | use distinct writable non-baseline paths | do not expose host paths or retain a partial pair |
| `evaluation_v2_cli_invalid` | CLI | `scripts.agent_evaluation_v2_gate._ArgumentParser.error` | use exactly `build` or `check` | do not print raw parser state |
| `evaluation_v2_public_output_unsafe` | public projection | `scripts.agent_evaluation_v2_contracts.validate_public_projection` | remove the field at its projection owner | do not redact after serialization |
| `evaluation_v2_internal_error` | boundary | `scripts.agent_evaluation_v2_gate.main` | reproduce with focused tests | do not expose exception text or traceback |

Coherent comparison stdout can also identify dataset drift, a missing
traversal checkpoint, an unexpected current-lane finding, multi-dimensional
control, control false green, non-responsible evaluator drift, application
projection drift, or JSON/Markdown drift. Fix the first owning symbol; never
weaken the expected finding or delete an application projection field.

## Code navigation

```text
scripts.agent_evaluation_v2_contracts.validate_dataset
scripts.agent_evaluation_v2_contracts.validate_report
scripts.agent_evaluation_v2_contracts.validate_comparison
scripts.agent_evaluation_v2_contracts.validate_public_projection
scripts.agent_evaluation_replay.ReplayHarness
scripts.agent_evaluation_replay.run_persisted_lane
scripts.agent_evaluation_v2_gate.build_semantic_comparison_projection
scripts.agent_evaluation_v2_gate.apply_control_mutation
scripts.agent_evaluation_v2_gate.evaluate_negative_control_sensitivity
scripts.agent_evaluation_v2_gate.build_report
scripts.agent_evaluation_v2_gate.render_markdown
scripts.agent_evaluation_v2_gate.compare_artifacts
scripts.agent_evaluation_v2_gate.write_artifacts_atomically
scripts.agent_evaluation_v2_gate._ArgumentParser.error
scripts.agent_evaluation_v2_gate.main
agent.harness_contracts.AgentHarness
api.run_repository.create_run
api.run_dispatch_repository.claim_run_dispatch
api.server._run_dispatched_with_persistence
api.research_execution_service.ResearchExecutionService.execute
api.run_repository.finalize_run_transaction
api.run_repository.get_run
api.run_result_service.resolve_run_result
scripts.agent_evaluation_context.project_context_reliability_outcome
scripts.agent_evaluation_context.compare_context_reliability_outcomes
scripts.agent_evaluation_contracts.validate_observation
scripts.agent_evaluation_evaluators.evaluate_observation
```

## Allowed claim

For three reviewed public-safe synthetic cases, DRA independently runs six
healthy replay anchors through its real application lifecycle and
deterministically proves that the responsible existing evaluator meaning
detects one declared post-traversal synthetic evaluator input control per pair
without provider or network access.

## Non-claims

This proof does not establish a production incident, automatic runtime
trajectory capture, automatic failure capture, case promotion, answer truth,
live-provider quality, arbitrary-task reliability, production scale, adoption,
business impact, generic DLP/PII/secret detection, exactly-once execution,
new model or multi-agent capability, API/UI/hosted evaluation readiness,
deployment readiness, or release inclusion.
