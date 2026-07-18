# Contributing

## Environment

Use Python 3.11 and the complete release lock:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps -r constraints.txt
```

Frontend changes also require Node.js `20.19+`, `22.12+`, or `24+`, matching
the locked Vite toolchain:

```bash
cd frontend
npm ci
```

Keep credentials and private configuration in `.env`. Never commit tokens,
cookies, runtime databases, output artifacts, local instruction state, or
provider payloads.

## Change Workflow

1. Read `AGENTS.md`, the affected implementation, tests, and current ADR or
   reference contract.
2. Keep the change scoped. Architecture and authority boundaries require an
   ADR update in the same pull request.
3. For behavior changes, write a failing regression or behavior test first,
   confirm the expected RED failure, then implement the smallest GREEN change.
4. Update public API, configuration, operations, and reference documentation
   with the behavior they describe.
5. Inspect the complete diff for unrelated edits and sensitive information.

## Test Tiers

Run focused tests while developing:

```bash
python -m pytest tests/unit/test_name.py -q
```

Run broader integration tests for persistence, concurrency, API, worker, or
framework-boundary changes. Use risk-based verification: a small, isolated
change normally needs focused checks, while broad, shared, or release-facing
work needs the complete relevant local checks. `.github/workflows/ci.yml` is
the authority for hosted gates; local commands do not establish hosted check
state. For broad, shared, or release-facing work, the local baseline is:

```bash
python -m pytest -q
python scripts/final_presentation_audit.py --root .
python scripts/check_canonical_identity.py --root .
git diff --check
```

For demo console changes, also run:

```bash
cd frontend
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
```

Run the durable HITL gate only when that controlled contract is affected and
Docker is available. Real-provider and benchmark runs remain explicit; required
CI tests must mock remote providers.

## Documentation

- Tutorials teach a complete first outcome.
- Operations guides describe repeatable procedures and recovery.
- Reference documents match current code and contract tests.
- ADRs explain durable ownership and trade-offs.
- The curated Superpowers workspace can retain active approved artifacts and
  selected completed implementation records. Completed records document prior
  implementation; they do not own the current contract.

Every relative Markdown link must resolve. Public claims require a producing
command, test, benchmark, or bounded evidence artifact.

## Pull Requests

Describe the final effect, acceptance-level completion, and commands actually
run. State skipped checks and remaining risk explicitly. Do not claim tests,
benchmarks, reviews, builds, or deployment results without current command
evidence. Before submission, verify the persisted PR title, body, base, head,
and draft state. Ensure the body matches the actual diff, commands, results,
scope, risks, and non-claims. Use ordinary bullets for completed facts.
Checkbox state is explicit: pending merge gates use `[ ]`; satisfied merge gates must be updated to `[x]`.

When completed CI, merge authorization, mergeability, review blockers, or
cleanup change the PR's terminal state, perform a final PR-body reconciliation
before reporting closeout. Replace stale pending language with the actual
terminal result and necessary links, update remaining risk, and preserve valid
non-claims. Then read back the persisted PR body and verify it matches the
intended final body. If either the update or persisted-body readback fails, you
must not report the PR as fully closed; record the exact blocker or pending
trigger instead.

The current supported surface and non-scope are recorded in the current
[release index](docs/README.md#release). Do not add deployment, public online
execution, frontend-owned business state, new runtime Skills, broad dependency
upgrades, or authority changes as incidental cleanup.
