# Release Evidence

This directory retains only bounded evidence used by current release gates.
Each artifact states its own scope and limits; presence in this directory does
not grant independent verification authority.

| Artifact | Boundary |
|---|---|
| [agent-evaluation-regression-v1.json](agent-evaluation-regression-v1.json) | Canonical deterministic Agent evaluation report for eight fixed cases and six evaluators; not runtime output or truth verification. |
| [agent-evaluation-regression-v1.md](agent-evaluation-regression-v1.md) | Human-readable rendering derived only from the validated JSON report. |
| [downstream-consumer-contract-v1.json](downstream-consumer-contract-v1.json) | Deterministic synthetic compatibility fixture for the versioned downstream status/result/Evidence boundary; it is not runtime output or independent verification. |
| [durable-hitl-gate-report.json](durable-hitl-gate-report.json) | Machine-readable result for the 13 controlled single-node SQLite durability and safety gates. |
| [real-source-proof.json](real-source-proof.json) | Machine-readable bounded real-source workflow proof and report hashes. |
| [real-source-proof.md](real-source-proof.md) | Human-readable proof procedure, verification/publication outcome, and explicit limitations. |
| [run-creation-idempotency-v1.json](run-creation-idempotency-v1.json) | Deterministic machine-readable lost-response identity reconciliation proof. |
| [run-creation-idempotency-v1.md](run-creation-idempotency-v1.md) | Human-readable cases and limits, including `crash_before_schedule_recovery: not_proven`. |
| [run-dispatch-reconciliation-v1.json](run-dispatch-reconciliation-v1.json) | Deterministic machine-readable single-node committed pre-start dispatch proof. |
| [run-dispatch-reconciliation-v1.md](run-dispatch-reconciliation-v1.md) | Human-readable cases and limits, including `commit_before_execution_start_recovery: proven` and `crash_before_schedule_recovery: proven`. |

The dispatch proof explicitly records `exactly_once_execution: not_claimed`,
`running_execution_recovery: not_proven`,
`provider_tool_side_effect_exactly_once: not_claimed`,
`multi_instance_high_availability: not_proven`, and
`live_provider_result: not_observed`.

The durable HITL artifact proves only the documented feasibility boundary; its
feature flag remains disabled by default. The real-source artifact proves a
small declared workflow sample, not source archiving, automatic truth
verification, market coverage, or hiring outcomes.

The downstream fixture is generated and strictly checked by
`scripts/downstream_consumer_contract.py`. Its reusable consumer and
failure-handling boundary is documented in
[`docs/reference/downstream-consumer-contract.md`](../reference/downstream-consumer-contract.md).
The Agent evaluation artifacts and baseline review workflow are documented in
[`docs/reference/agent-evaluation-regression-gate.md`](../reference/agent-evaluation-regression-gate.md).
