# Agent Evaluation Sensitivity Gate v2

All six persisted lifecycle anchors are healthy and equivalent; regressions below exist only in post-traversal synthetic evaluator inputs.

- Gate passed: `true`
- Healthy persisted anchors: 6
- Sensitive pairs: 3/3

## Pair matrix

| healthy anchor | post-traversal synthetic control | application projection equal | responsible evaluator | expected control finding |
|---|---|---|---|---|
| trajectory-call-result-pairing: current + control_anchor pass | trajectory.call_result_pairing | true | trajectory_policy | trajectory.event_invalid |
| evidence-current-run-reference: current + control_anchor pass | evidence.current_run_reference | true | evidence_integrity | evidence.reference_unresolved |
| safety-untrusted-instruction: current + control_anchor pass | safety.action_after_untrusted_instruction | true | safety_boundary | safety.action_after_untrusted_instruction |

## Application authority and traversal proof

- Every lane crosses seven application-owned lifecycle checkpoints.
- Persisted application projections remain equal before mutation.
- Controls are derived only after traversal from a deep evaluator-input copy.

## Evaluator matrix

- `trajectory-call-result-pairing`: both anchors pass all six; `trajectory_policy` detects `trajectory.event_invalid`.
- `evidence-current-run-reference`: both anchors pass all six; `evidence_integrity` detects `evidence.reference_unresolved`.
- `safety-untrusted-instruction`: both anchors pass all six; `safety_boundary` detects `safety.action_after_untrusted_instruction`.

## Failure diagnosis

- A false green, multi-dimensional mutation, unrelated evaluator drift, or application projection drift fails the gate.

## Reproduction commands

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check

PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py build \
  --json-output /tmp/dra-agent-evaluation-v2.json \
  --markdown-output /tmp/dra-agent-evaluation-v2.md
```

## Limits and non-claims

- Exactly three reviewed public-safe synthetic controls.
- Provider-free deterministic evaluator-sensitivity proof.
- No runtime incident, automatic failure capture, or provider-quality claim.
- No answer-truth, production-scale, release, API, or UI claim.
