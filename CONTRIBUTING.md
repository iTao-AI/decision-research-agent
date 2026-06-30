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
framework-boundary changes. Before requesting review, run:

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
- Active approved project plans belong in the curated Superpowers workspace;
  completed implementation history belongs in Git after durable decisions are
  promoted.

Every relative Markdown link must resolve. Public claims require a producing
command, test, benchmark, or bounded evidence artifact.

## Pull Requests

Describe the final effect, acceptance-level completion, and commands actually
run. State skipped checks and remaining risk explicitly. Do not claim tests,
benchmarks, reviews, builds, or deployment results without current command
evidence.

The v0.1.0 release boundary is backend and CLI; the repository now also carries
a separately built Agent Research Operations Console. Do not add deployment,
public online execution, frontend-owned business state, new runtime Skills,
broad dependency upgrades, or authority changes as incidental cleanup.
