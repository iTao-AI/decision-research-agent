# Durable Run Failure Cause v1 Proof

Status: valid deterministic local production-path contract proof.

## Cases

| Case | Phase | Code | Status |
|---|---|---|---|
| `completed_null` | `none` | `none` | passed |
| `historical_not_observed` | `none` | `none` | passed |
| `dispatch_schedule_failed` | `dispatch` | `run_dispatch_schedule_failed` | passed |
| `dispatch_start_failed` | `dispatch` | `run_dispatch_start_failed` | passed |
| `dispatch_start_timeout` | `dispatch` | `run_dispatch_start_timeout` | passed |
| `dispatch_lease_expired` | `dispatch` | `run_dispatch_lease_expired` | passed |
| `execution_call_budget_exceeded` | `execution` | `call_budget_exceeded` | passed |
| `execution_recursion_limit_exceeded` | `execution` | `recursion_limit_exceeded` | passed |
| `execution_invalid_research_packet` | `execution` | `invalid_research_packet` | passed |
| `execution_missing_research_packet` | `execution` | `missing_research_packet` | passed |
| `execution_timeout` | `execution` | `run_timeout` | passed |
| `finalization_timeout` | `finalization` | `run_timeout` | passed |
| `execution_cancelled` | `execution` | `cancelled` | passed |
| `finalization_cancelled` | `finalization` | `cancelled` | passed |
| `execution_error` | `execution` | `execution_error` | passed |
| `finalization_failed` | `finalization` | `run_finalization_failed` | passed |

## Invariants

- `retry_attempts_have_no_cause`: passed
- `dispatch_codes_match`: passed
- `terminal_insert_fault_rolls_back`: passed
- `terminal_guards_fail_closed`: passed
- `first_cause_is_immutable`: passed
- `restart_projection_is_identical`: passed
- `termination_ownership_is_distinct`: passed
- `prestart_cancellation_is_infrastructure_only`: passed
- `inner_self_cancel_is_bounded`: passed
- `launched_terminal_task_settles`: passed
- `public_failure_surface_is_redacted`: passed
- `bounded_cli_inputs_fail_closed`: passed
- `fresh_outputs_are_byte_identical`: passed

## Boundaries

- `application_database_terminal_authority: proven`
- `production_scheduler_timeout_cancellation: proven`
- `framework_native_signal_mapping: proven`
- `status_projection_after_restart: proven`
- `result_and_downstream_v1_compatibility: separate_gate`
- `live_provider_result: not_observed`
- `external_side_effect_exactly_once: not_claimed`

## Limits

- Deterministic local production-path contract proof, not a live-provider measurement.
- SQLite single-node terminal authority is proven; multi-instance operation is not claimed.
- Result and downstream v1 compatibility remain owned by their separate regression gates.
