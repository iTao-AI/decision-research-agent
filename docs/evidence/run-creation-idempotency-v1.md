# Run Creation Idempotency v1 Proof

Status: valid deterministic local contract proof.

| Case | Status |
|---|---|
| `lost_response_replay` | passed |
| `request_conflict` | passed |
| `concurrent_duplicate_serialization` | passed |
| `durable_restart_lookup` | passed |
| `unkeyed_independence` | passed |
| `raw_key_non_persistence` | passed |
| `tool_client_key_recovery` | passed |

## Boundaries

- `client_response_loss_after_scheduling: proven`
- `durable_identity_lookup_after_restart: proven`
- `crash_before_schedule_recovery: not_proven`
- `exactly_once_execution: not_claimed`

## Limits

- Deterministic local contract proof, not a provider or production measurement.
- Response loss is simulated only after current-process scheduling completes.
- Process or handler failure before scheduling is not recovered by this design.
