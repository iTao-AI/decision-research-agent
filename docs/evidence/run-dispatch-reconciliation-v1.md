# Run Dispatch Reconciliation v1 Proof

Status: valid deterministic local contract proof.

| Case | Status |
|---|---|
| `atomic_create` | passed |
| `commit_before_schedule_recovery` | passed |
| `handler_cancellation_recovery` | passed |
| `worker_restart_recovery` | passed |
| `expired_lease_reclaim` | passed |
| `concurrent_dispatch_fence` | passed |
| `stale_task_blocked` | passed |
| `scheduler_exhaustion` | passed |
| `keyed_replay_single_agent_entry` | passed |
| `unkeyed_compatibility` | passed |
| `contract_compatibility` | passed |
| `migration_safety` | passed |

## Boundaries

- `commit_before_execution_start_recovery: proven`
- `crash_before_schedule_recovery: proven`
- `single_node_sqlite_dispatch_reconciliation: proven`
- `exactly_once_execution: not_claimed`
- `running_execution_recovery: not_proven`
- `provider_tool_side_effect_exactly_once: not_claimed`
- `multi_instance_high_availability: not_proven`
- `live_provider_result: not_observed`

## Limits

- Deterministic single-node SQLite contract proof, not a provider or production measurement.
- Recovery is proven only before application-owned execution start.
- Agent, provider, and tool side effects remain outside an exactly-once guarantee.
