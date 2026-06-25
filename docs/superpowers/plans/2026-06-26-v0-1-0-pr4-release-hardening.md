# v0.1.0 PR4 Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Coding
> subagents are disabled by repository policy. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Turn the cleaned backend-and-CLI repository into a reproducible,
documented, release-ready `v0.1.0` without creating the tag or GitHub Release.

**Architecture:** Freeze verified dependency versions, audit dead dependencies,
align every current document with the canonical runtime, and run the complete
backend, durability, Docker, proof, consumer, security, and documentation gate.

**Tech Stack:** Python 3.11, pip constraints, FastAPI, LangChain/DeepAgents/
LangGraph/LangSmith, pytest, Docker Compose, GitHub Actions, CodeQL.

---

## Delivery Boundary

Included:

- clean constraints install and version report;
- dependency audit and evidence-based removal;
- complete README/architecture/API/operations/security documentation;
- `VERSION=0.1.0` and CHANGELOG release entry;
- release notes and breaking migration guide;
- final metrics refreshed from actual commands;
- complete release verification.

Excluded:

- React;
- feature expansion;
- tag, GitHub Release, deployment, or public announcement without separate
  authorization.

## Task 1: Verify and Freeze the Clean Dependency Environment

**Files:**

- Modify only when evidence requires: `requirements.txt`, `constraints.txt`,
  `Dockerfile.backend`.
- Create: `scripts/report_runtime_versions.py`
- Create: `tests/unit/test_runtime_versions.py`

- [ ] **Step 1: Create a clean virtual environment**

```bash
python3.11 -m venv .release-venv
.release-venv/bin/python -m pip install --upgrade pip
.release-venv/bin/pip install -r requirements.txt -c constraints.txt
```

Expected: installation succeeds without using the developer `.venv`.

- [ ] **Step 2: Add deterministic version report**

The script prints JSON for:

```text
python
deepagents
langchain
langchain-core
langgraph
langgraph-checkpoint-sqlite
langsmith
fastapi
pydantic
```

The test compares installed package versions with `constraints.txt`.

- [ ] **Step 3: Run tests in the clean environment**

```bash
.release-venv/bin/python -m pytest -q
```

- [ ] **Step 4: Audit dependencies**

For every candidate deletion, require:

```bash
rg -n '<import-or-package-name>' agent api tools scripts tests
.release-venv/bin/python -m pytest -q
docker compose build backend
```

Remove PDF/Word/spreadsheet/WeasyPrint dependencies only when active imports,
tests, and Docker build prove they are unused after the upload/download and PDF
Agent tools are removed.

- [ ] **Step 5: Commit**

```bash
git commit -m "build(release): verify v0.1.0 dependencies"
```

## Task 2: Rewrite Current Product Documentation

**Files:**

- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `AGENTS.md`
- Modify: `docs/README.md`
- Modify: `docs/prd.md`
- Modify: `spec/README.md`
- Modify: `spec/architecture.md`
- Modify: `spec/api-contract.md`
- Modify: `spec/data-models.md`
- Modify: `spec/state-machine.md`
- Modify: `spec/tool-registry.md`
- Modify: `docs/observability.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify current `docs/operations/*`

- [ ] **Step 1: Add documentation contract tests**

Check current docs contain:

```text
LangChain = Agent Framework
DeepAgents = research harness
LangGraph = durable workflow runtime
LangSmith = privacy-first tracing/evaluation
Application DB = business authority
```

Check they do not advertise Vue, task routes, legacy env, old health identity,
host output paths, PDF Agent generation, persistent Agent memory, or generic
research kill-9 resume.

- [ ] **Step 2: Rewrite README first-run flow**

Target:

1. clone;
2. create `.env` from `.env.example`;
3. install with constraints;
4. start backend;
5. healthcheck/doctor;
6. create run and retrieve result.

Examples must be copy-paste complete and use canonical env/commands.

- [ ] **Step 3: Update architecture and limitations**

Include:

- `ResearchExecutionService -> AgentHarness -> DeepAgentsHarness`;
- generic VFS/Skills/compiled researchers;
- bounded Talent direct LangChain path;
- application ledger vs LangGraph checkpoint vs LangSmith;
- durable review and Evidence verification boundaries;
- main research does not resume an interrupted tool call after process death;
- backend-and-CLI release, React deferred.

- [ ] **Step 4: Update operations**

Document:

- canonical DB migration and rollback;
- explicit legacy table archive/drop;
- review/verification flags default false;
- privacy-first trace defaults;
- result endpoint error codes;
- no frontend service.

- [ ] **Step 5: Run doc tests and commit**

```bash
.release-venv/bin/python -m pytest \
  tests/unit/test_documentation_contracts.py -q
git diff --check
git commit -m "docs(release): align v0.1.0 documentation"
```

## Task 3: Prepare Version, Changelog, and Release Notes

**Files:**

- Modify: `VERSION`
- Modify: `CHANGELOG.md`
- Modify: `SECURITY.md`
- Create: `docs/releases/v0.1.0.md`
- Create: `tests/unit/test_release_metadata.py`

- [ ] **Step 1: Write metadata RED tests**

Assert:

```python
assert Path("VERSION").read_text().strip() == "0.1.0"
assert "## [0.1.0]" in Path("CHANGELOG.md").read_text()
assert "Breaking Changes" in Path("docs/releases/v0.1.0.md").read_text()
```

Also assert release notes mention the migration command, canonical DB/env,
removed routes/CLI/frontend, rollback, and supported backend-and-CLI boundary.

- [ ] **Step 2: Run RED**

```bash
.release-venv/bin/python -m pytest \
  tests/unit/test_release_metadata.py -q
```

- [ ] **Step 3: Write release metadata**

Use actual merged behavior and actual verification counts only. Do not copy old
benchmark numbers as current stability metrics.

- [ ] **Step 4: Run GREEN and commit**

```bash
.release-venv/bin/python -m pytest \
  tests/unit/test_release_metadata.py -q
git commit -m "chore(release): prepare v0.1.0 metadata"
```

## Task 4: Run the Complete Release Gate

**Files:** update evidence/docs only when produced by a required command.

- [ ] **Step 1: Backend and identity**

```bash
.release-venv/bin/python scripts/check_canonical_identity.py
.release-venv/bin/python -m pytest -q
git diff --check
```

- [ ] **Step 2: Durable gates**

Run serially:

```bash
.release-venv/bin/python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json
.release-venv/bin/python scripts/real_source_proof.py check-report \
  --report docs/evidence/p2a-real-source-proof.json
```

Expected: durable `13/13 PASS`, proof report `valid`.

- [ ] **Step 3: Docker**

```bash
docker compose build backend
docker compose up -d mysql backend
curl --fail --silent http://127.0.0.1:8000/health
docker compose down -v
```

Expected health:

```json
{"status":"ok","service":"decision-research-agent"}
```

Run durable Docker compatibility and Evidence verification canary tests
serially to avoid Compose resource/report races.

- [ ] **Step 4: Tool Client and consumer**

Run:

```bash
.release-venv/bin/python tools/decision_research_agent_tool.py doctor
```

Then repeat the bounded first-party run/result smoke with a non-printed key.
Verify no secret in stdout, stderr, logs, or diff.

- [ ] **Step 5: Documentation and security**

Run the repository link checker or add one if absent. Run:

```bash
git grep -nE '(API_KEY|SECRET|TOKEN)=([^.$<{].+)' -- ':!*.example'
.release-venv/bin/python scripts/check_canonical_identity.py
```

Inspect Dependabot/security alerts separately; do not bundle unrelated major
dependency upgrades into this PR.

- [ ] **Step 6: Record exact evidence**

Update README/release notes only with fresh command output:

- test count;
- durable gate status;
- Docker checks;
- proof checker;
- installed framework versions.

- [ ] **Step 7: Commit generated release evidence**

```bash
git commit -m "test(release): record v0.1.0 verification"
```

## Task 5: Pre-Release Review and PR Preparation

- [ ] **Step 1: Run documentation audit**

Use `gstack-document-release` because this PR changes public architecture,
installation, API, migration, and release documentation.

- [ ] **Step 2: Run lightweight pre-landing review**

Focus on release metadata, migration safety, secret exposure, documentation
drift, and dependency claims. Do not repeat the full architecture autoplan.

- [ ] **Step 3: Verify clean branch**

```bash
git status --short
git log --oneline main..HEAD
git diff --check main...HEAD
```

- [ ] **Step 4: Prepare result-first PR body**

Include:

- Summary;
- Completion checklist;
- exact Verification table;
- breaking migration and rollback;
- explicit no React/deployment/tag scope;
- documentation impact.

## PR4 Final Gate

The PR may be created only when:

- clean constraints install passes;
- full pytest passes;
- canonical identity scan passes;
- durable gate is `13/13 PASS`;
- durable Docker compatibility passes;
- Evidence verification canary passes;
- real-source proof checker is valid;
- backend Docker build and canonical health pass;
- Tool Client doctor and consumer run/result smoke pass;
- documentation audit and link check pass;
- CI and CodeQL pass after PR creation;
- worktree is clean.

Tag, GitHub Release, deployment, and public announcement remain separate
explicitly authorized actions.
