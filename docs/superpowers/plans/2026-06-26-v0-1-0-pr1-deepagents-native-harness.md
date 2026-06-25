# v0.1.0 PR1 DeepAgents-Native Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Coding
> subagents are disabled by repository policy. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Replace custom Agent harness plumbing with a DeepAgents-native
implementation behind an application-owned interface without changing public
API, database schema, or delivery semantics.

**Architecture:** `ResearchExecutionService` owns the accumulator and invokes an
`AgentHarness` port. `DeepAgentsHarness` compiles the generic coordinator,
LangChain researchers, VFS, Skills, runtime context, and Middleware, then
returns an application-owned `ExecutionOutcome`.

**Tech Stack:** Python 3.11, LangChain 1.3.10, DeepAgents 0.6.11, LangGraph
1.2.6, pytest.

---

## Delivery Boundary

Included:

- `AgentHarness`, request/context/outcome contracts;
- DeepAgents adapter and profile factory;
- three LangChain `CompiledSubAgent` researchers;
- `CompositeBackend` with run-scoped `StateBackend` and read-only Skills route;
- built-in DeepAgents Middleware compatibility assertions;
- model/tool budgets using LangChain Middleware;
- two checked-in generic Skills;
- removal of custom subagent classes, `SharedContext`, host report tools, PDF
  Agent tool, and host-reading upload Agent tool;
- temporary legacy finalizer adaptation to normalized report content.

Excluded:

- public API or database schema changes;
- canonical result endpoint and generic run artifacts;
- task/thread route removal;
- environment/database rename;
- Vue removal;
- persistent StoreBackend, Async Subagents, ContextSeek, LLM reviewer, or
  main-research crash resume.

## File Map

### Create

- `agent/harness_contracts.py`
- `agent/runtime_context.py`
- `agent/profile_middleware.py`
- `agent/research_agents.py`
- `agent/deepagents_harness.py`
- `api/research_execution_service.py`
- `skills/research-planning/SKILL.md`
- `skills/evidence-synthesis-and-reporting/SKILL.md`
- `tests/unit/test_harness_contracts.py`
- `tests/unit/test_runtime_context.py`
- `tests/unit/test_profile_middleware.py`
- `tests/unit/test_research_agents.py`
- `tests/unit/test_deepagents_harness.py`
- `tests/integration/test_harness_execution.py`

### Modify

- `agent/main_agent.py`
- `agent/profile_agents.py`
- `agent/profile_registry.py`
- `agent/run_result.py`
- `agent/research.py`
- `tools/tavily_tools.py`
- `api/server.py`
- `api/task_finalizer.py`
- `Dockerfile.backend`
- `.dockerignore`
- affected lifecycle, isolation, profile, delegation, upload, and finalizer
  tests.

### Delete After Parity

- `agent/shared_context.py`
- `agent/sub_agents/base.py`
- `agent/sub_agents/database_query_agent.py`
- `agent/sub_agents/knowledge_base_agent.py`
- `agent/sub_agents/network_search_agent.py`
- `tools/shared_context_tools.py`
- `tools/markdown_tools.py`
- `tools/pdf_tools.py`
- `tools/upload_file_read_tool.py`
- tests whose only purpose is the deleted implementation.

## Task 1: Define the Application Harness Port

**Files:**

- Create: `agent/harness_contracts.py`
- Create: `agent/runtime_context.py`
- Test: `tests/unit/test_harness_contracts.py`
- Test: `tests/unit/test_runtime_context.py`

- [ ] **Step 1: Write contract RED tests**

```python
from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath

import pytest

from agent.harness_contracts import HarnessRequest, ReportCandidate
from agent.runtime_context import ResearchRuntimeContext


def test_harness_request_is_immutable():
    request = HarnessRequest(
        query="research agent hiring signals",
        thread_id="thread_1",
        run_id="run_1",
        segment_id="segment_1",
        profile_id="generic",
        scope={},
    )
    with pytest.raises(FrozenInstanceError):
        request.run_id = "other"


def test_report_candidate_accepts_only_virtual_workspace_path():
    candidate = ReportCandidate(
        path=PurePosixPath("/workspace/research-report.md"),
        content="# Report",
    )
    assert candidate.path.as_posix() == "/workspace/research-report.md"


def test_runtime_context_normalizes_policy_to_tuples():
    context = ResearchRuntimeContext(
        thread_id="thread_1",
        run_id="run_1",
        segment_id="segment_1",
        profile_id="generic",
        allowed_source_domains=["example.com"],
        allowed_source_types=["public_web"],
        allowed_aggregate_ids=[],
    )
    assert context.allowed_source_domains == ("example.com",)
```

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_harness_contracts.py \
  tests/unit/test_runtime_context.py -q
```

Expected: collection fails because the new modules do not exist.

- [ ] **Step 3: Implement frozen contracts**

Define:

```python
@dataclass(frozen=True)
class HarnessRequest:
    query: str
    thread_id: str
    run_id: str
    segment_id: str
    profile_id: str
    scope: Mapping[str, Any]


@dataclass(frozen=True)
class ReportCandidate:
    path: PurePosixPath
    content: str
```

Keep `ExecutionOutcome` application-owned in `agent/run_result.py`; extend it
with `report_candidate: ReportCandidate | None` and remove `session_dir` only
after all callers use the new field.

Define `ResearchRuntimeContext` as a frozen dataclass that converts all policy
collections to tuples in `__post_init__`.

- [ ] **Step 4: Run GREEN**

Run the same command. Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add \
  agent/harness_contracts.py \
  agent/runtime_context.py \
  tests/unit/test_harness_contracts.py \
  tests/unit/test_runtime_context.py
git commit -m "feat(agent): define harness execution contracts"
```

## Task 2: Compile Server-Owned Middleware and Researchers

**Files:**

- Create: `agent/profile_middleware.py`
- Create: `agent/research_agents.py`
- Modify: `agent/profile_registry.py`
- Test: `tests/unit/test_profile_middleware.py`
- Test: `tests/unit/test_research_agents.py`
- Modify: `tests/unit/test_profile_registry.py`

- [ ] **Step 1: Write middleware and researcher RED tests**

Assert exact server-owned limits:

```python
def test_generic_coordinator_limits_are_fail_closed():
    middleware = build_profile_middleware("generic", role="coordinator")
    assert middleware_contract(middleware) == {
        "model_run_limit": 40,
        "global_tool_run_limit": 40,
        "task_run_limit": 8,
        "exit_behavior": "error",
    }


def test_network_researcher_has_only_network_tools():
    compiled = compile_generic_researchers(model=FakeModel())
    researcher = compiled["network_search"]
    assert researcher.tool_names == {
        "internet_search",
    }
```

Add equivalent exact assertions for database and knowledge researchers. Assert
the generic profile excludes `general-purpose`, uses the two Skills, and has
the first-match-wins filesystem permission contract from the spec.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_profile_middleware.py \
  tests/unit/test_research_agents.py \
  tests/unit/test_profile_registry.py -q
```

Expected: imports or assertions fail against the current custom wrappers.

- [ ] **Step 3: Implement Middleware compiler**

Use real LangChain Middleware:

```python
ModelCallLimitMiddleware(run_limit=40, exit_behavior="error")
ToolCallLimitMiddleware(run_limit=40, exit_behavior="error")
ToolCallLimitMiddleware(
    tool_name="task",
    run_limit=8,
    exit_behavior="error",
)
```

Researchers use model limit `20` and tool limit `12`; Talent uses model limit
`12` and exposes no tool limiter because it has no tools.

- [ ] **Step 4: Compile researchers**

Use `langchain.agents.create_agent` with explicit name, prompt, tools,
`context_schema=ResearchRuntimeContext`, and role middleware. Register the
compiled runnables using DeepAgents `CompiledSubAgent`; do not wrap them in
custom classes or module-level singleton instances.

- [ ] **Step 5: Update immutable profile policies**

Set generic policy to:

```python
backend="composite-state-skills-v1"
allowed_tools=("write_todos", "ls", "read_file", "glob", "grep",
               "write_file", "edit_file", "task")
subagents=("knowledge_base", "database_query", "network_search")
skills=(
    "/skills/research-planning/",
    "/skills/evidence-synthesis-and-reporting/",
)
```

Keep Talent tools/subagents/skills empty and deny all filesystem operations.

- [ ] **Step 6: Run GREEN and commit**

Run the focused command, then:

```bash
git add \
  agent/profile_middleware.py \
  agent/research_agents.py \
  agent/profile_registry.py \
  tests/unit/test_profile_middleware.py \
  tests/unit/test_research_agents.py \
  tests/unit/test_profile_registry.py
git commit -m "feat(agent): compile bounded research agents"
```

## Task 3: Add Read-Only Skills and Composite Backend

**Files:**

- Create: `skills/research-planning/SKILL.md`
- Create: `skills/evidence-synthesis-and-reporting/SKILL.md`
- Create: `agent/deepagents_harness.py`
- Test: `tests/unit/test_deepagents_harness.py`
- Modify: `Dockerfile.backend`
- Modify: `.dockerignore`

- [ ] **Step 1: Write backend and Skill RED tests**

Test the real configured backend:

```python
def test_generic_backend_routes_skills_read_only():
    harness = build_generic_harness(model=FakeModel())
    assert harness.backend_contract() == {
        "default": "StateBackend",
        "routes": {"/skills/": "FilesystemBackend"},
        "virtual_mode": True,
    }
    assert harness.can_write("/workspace/note.md")
    assert not harness.can_write("/skills/research-planning/SKILL.md")
    assert not harness.can_read("/etc/passwd")


def test_generic_skills_are_real_and_talent_has_none():
    assert load_skill_names("generic") == {
        "research-planning",
        "evidence-synthesis-and-reporting",
    }
    assert load_skill_names("talent-hiring-signal") == set()
```

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_deepagents_harness.py -q
```

- [ ] **Step 3: Write public-neutral Skills**

`research-planning` must require:

- create a bounded plan before research;
- delegate only to named researchers;
- select sources according to server policy;
- record gaps instead of inventing facts.

`evidence-synthesis-and-reporting` must require:

- synthesize only returned tool/subagent content;
- separate findings, limitations, contradictions, and recommendations;
- write exactly `/workspace/research-report.md`;
- never claim verification not present in Evidence state.

- [ ] **Step 4: Implement backend and permissions**

Build:

```python
CompositeBackend(
    default=StateBackend(),
    routes={
        "/skills/": FilesystemBackend(
            root_dir=repository_skills_root,
            virtual_mode=True,
        ),
    },
)
```

Use exact ordered permissions:

1. deny writes `/skills/**`;
2. allow reads `/skills/**`;
3. allow reads/writes `/workspace/**`;
4. deny reads/writes `/**`.

Disable the default general-purpose subagent through the pinned DeepAgents
harness profile contract. Explicitly compatibility-test the built-in
`TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`,
`SubAgentMiddleware`, and `PatchToolCallsMiddleware`.

- [ ] **Step 5: Package Skills**

Add `COPY skills/ skills/` to `Dockerfile.backend`. Ensure `.dockerignore`
does not exclude the directory.

- [ ] **Step 6: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest tests/unit/test_deepagents_harness.py -q
git add \
  agent/deepagents_harness.py \
  skills/research-planning/SKILL.md \
  skills/evidence-synthesis-and-reporting/SKILL.md \
  tests/unit/test_deepagents_harness.py \
  Dockerfile.backend \
  .dockerignore
git commit -m "feat(agent): adopt DeepAgents workspace harness"
```

## Task 4: Route Execution Through ResearchExecutionService

**Files:**

- Create: `api/research_execution_service.py`
- Modify: `agent/main_agent.py`
- Modify: `agent/profile_agents.py`
- Modify: `agent/run_result.py`
- Modify: `agent/research.py`
- Modify: `tools/tavily_tools.py`
- Modify: `api/task_finalizer.py`
- Test: `tests/integration/test_harness_execution.py`
- Modify: lifecycle, isolation, timeout, Talent, and finalizer tests.

- [ ] **Step 1: Write service RED tests**

Use a fake `AgentHarness` to prove:

- request identity and server policy are passed exactly;
- outcome Evidence is frozen before cleanup;
- timeout/cancellation publish the latest outcome;
- `call_budget_exceeded` remains stable;
- report candidate is exact `/workspace/research-report.md`;
- legacy finalization consumes outcome content rather than scanning a host
  directory.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/unit/test_task_finalizer.py -q
```

- [ ] **Step 3: Implement the service**

`ResearchExecutionService.execute()` must:

1. create `AgentRunAccumulator`;
2. preload declared Talent aggregate Evidence;
3. build immutable runtime context;
4. invoke `AgentHarness.execute()`;
5. merge/freeze Evidence and diagnostics;
6. publish `OutcomeBox`;
7. clear run-scoped caches in `finally`.

Do not expose repositories to the harness.

- [ ] **Step 4: Reduce `agent/main_agent.py`**

Keep a compatibility entry function:

```python
async def run_deep_agent(...):
    return await research_execution_service.execute(...)
```

Remove module-level DeepAgent compilation, host workspace preparation,
`SharedContext`, ContextVar policy setup that is now runtime context, and
filesystem instructions.

- [ ] **Step 5: Adapt temporary legacy finalization**

During PR1/PR2, write legacy output files only from
`outcome.report_candidate.content` or bounded fallback content. Do not scan
`session_dir`.

- [ ] **Step 6: Run GREEN**

Run the focused command plus:

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_context_isolation.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_api.py \
  tests/unit/test_talent_search.py \
  tests/unit/test_talent_artifacts.py -q
```

- [ ] **Step 7: Commit**

Stage only affected files and commit:

```bash
git commit -m "refactor(agent): isolate DeepAgents execution"
```

## Task 5: Delete Superseded Harness Code

**Files:** deletion set from File Map plus affected tests and imports.

- [ ] **Step 1: Add absence assertions**

Add a deterministic architecture test that scans active Python files and fails
on:

```text
agent.shared_context
tools.shared_context_tools
generate_markdown
convert_md_to_pdf
read_file_content
BaseAgent
AgentConfig
_resolve_subagent
```

- [ ] **Step 2: Run RED**

Expected: the scan identifies current imports/files.

- [ ] **Step 3: Delete superseded modules and tests**

Delete only after the service and adapter tests pass. Remove the PDF conversion
dependencies only in PR4 after a dependency audit; PR1 deletes the Agent tool,
not necessarily the underlying utility package.

- [ ] **Step 4: Run focused and full verification**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_harness_execution.py \
  tests/integration/test_evidence_lifecycle.py \
  tests/integration/test_context_isolation.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_run_api.py -q
../../.venv/bin/python -m pytest -q
git diff --check
```

Expected: all pass; no API/schema snapshots change except profile manifests
explicitly approved by this PR.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(agent): remove legacy harness plumbing"
```

## PR1 Final Gate

- [ ] Full pytest passes.
- [ ] Docker backend builds with Skills included.
- [ ] Existing `/api/task`, `/api/runs`, and database schemas remain available
  and behavior-compatible for this PR.
- [ ] Talent has no Skills, VFS tools, uploads, memory, or subagents.
- [ ] Concurrent generic runs have isolated VFS/runtime context.
- [ ] Evidence survives timeout and cancellation.
- [ ] LangSmith disabled does not affect persistence.
- [ ] `git diff --check` passes.
- [ ] Worktree is clean after commits.
