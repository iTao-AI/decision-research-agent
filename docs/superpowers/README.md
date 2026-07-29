# Superpowers Workspace

This directory stores active, approved, public-neutral specifications and plans
and selected retained completed implementation records. Current release records
are in [docs/releases](../releases/).

This directory is artifact storage, not a workflow phase or current contract
authority. Code and tests are the primary implementation authority. Accepted
architecture decisions and current reference documentation outrank plans when
they conflict. Historical skill or subagent instructions describe their
original execution only and do not override the current repository
[`AGENTS.md`](../../AGENTS.md).

When implementation finishes, promote durable decisions into ADRs or reference
documentation. Retained completed records remain implementation history, not
current authority. Do not delete or rewrite historical specifications or plans
solely because they are complete.

Private rationale, raw prompts, transcripts, local paths, generated review
artifacts, and tool-specific restore data never belong in this directory.

## Current Crash-Safe Recovery Records

- [Approved design](specs/2026-07-28-crash-safe-agent-run-recovery-v1-design.md)
- [Approved implementation plan](plans/2026-07-29-crash-safe-startup-convergence-v1-implementation-plan.md)
- [Current operator runbook](../operations/run-execution-recovery.md)

The spec and plan are implementation records; current code, tests, ADRs,
reference contracts, and the runbook remain authoritative.
