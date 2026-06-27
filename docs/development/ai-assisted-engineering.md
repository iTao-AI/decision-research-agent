# AI-Assisted Engineering

Decision Research Agent uses AI-assisted engineering as a bounded development
workflow. Repository contracts, tests, human review, and release gates decide
what ships; model output does not.

```text
Problem definition
-> approved spec
-> scoped implementation plan
-> TDD
-> independent review
-> deterministic verification
-> PR and release gate
```

## Controls

1. Current code, tests, ADRs, and reference documentation define the working
   contract. Plans are subordinate when they conflict.
2. Behavior changes start with a failing test. The smallest implementation is
   added before broader regression checks.
3. Review checks scope, authority boundaries, error behavior, security, and
   evidence for public claims.
4. Deterministic commands produce repository-visible evidence. A passing model
   response or review summary is not verification.
5. Publication and release actions remain separately authorized operations.

## Repository Evidence

- The fixed-sample Talent value gate records the bounded benchmark decision.
- The durable HITL runner evaluates 13 durability and safety gates.
- Evidence, review, verification, publication, and delivery contracts fail
  closed in code and tests.
- The canonical identity and final presentation audits reject stale or private
  public surfaces.
- CI installs the Python 3.11 release lock and runs the backend suite.

These checks establish bounded properties only. They do not make AI an
acceptance authority, prove all Evidence true, or establish production
readiness beyond the documented release boundary.

## Project-Local Planning

Active approved work can be recovered from the curated
[Superpowers workspace](../superpowers/README.md). The current release cleanup
is tracked in its [public-neutral execution plan](../superpowers/plans/2026-06-27-v0-1-0-release-presentation-cleanup.md).
Completed implementation history is removed after durable decisions are
promoted into ADRs and current reference documentation; Git retains the
history.
