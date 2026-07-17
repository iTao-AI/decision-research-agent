# AI-Assisted Engineering

Decision Research Agent uses AI-assisted engineering as a bounded development
workflow. Repository contracts, tests, human review, and release gates decide
what ships; model output does not.

## Controls

1. Classify risk before choosing a workflow. Local changes use focused
   verification; broad, shared, release-facing, or authority-affecting work
   receives full relevant verification and review.
2. Current project code, diffs, tests, Git state, ADRs, and reference
   documentation are the authority. Plans are subordinate when they conflict.
3. Use a spec and implementation plan only for contract, architecture, or
   multi-module work. Behavior changes start with TDD: a failing test before
   the smallest implementation and broader regression checks.
4. Match review depth to risk, checking scope, authority boundaries, error
   behavior, security, and evidence for public claims.
5. Use conditional parallelism only when ownership and verification boundaries
   are clear. The parent owns integration, full relevant verification, and one
   consolidated terminal handoff.
6. Use one primary workflow controller per phase. Query external state only a
   bounded number of times; do not poll unchanged state indefinitely.
7. Deterministic commands produce repository-visible evidence. A passing model
   response or review summary is not verification. Publication and release
   actions remain separately authorized operations.

## Repository Evidence

- The fixed-sample Talent value gate records the bounded benchmark decision.
- The durable HITL runner evaluates 13 durability and safety gates.
- Evidence, review, verification, publication, and delivery contracts fail
  closed in code and tests.
- The canonical identity and final presentation audits reject stale or private
  public surfaces.
- CI runs deterministic proofs for Agent evaluation regression, run creation
  idempotency, run dispatch reconciliation, and terminal failure causes.
- Backend and frontend CI run the repository's required hosted checks.

The current [CI workflow](../../.github/workflows/ci.yml) is the authority for
hosted gates. This guide does not duplicate check names that can change.

These checks establish bounded properties only. They do not make AI an
acceptance authority, prove all Evidence true, or establish production
readiness beyond the documented release boundary.

## Project-Local Planning

Active approved work can be recovered from the curated
[Superpowers workspace](../superpowers/README.md). Current release records are
in [docs/releases](../releases/). Retained plans document implementation
history; they are not current contract authority. Promote durable decisions
into ADRs and current reference documentation.
