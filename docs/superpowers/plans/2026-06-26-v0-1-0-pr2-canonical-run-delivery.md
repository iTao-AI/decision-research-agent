# v0.1.0 PR2 Canonical Run Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Coding
> subagents are disabled by repository policy. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Make `/api/runs` the complete first-party execution path by
persisting a canonical generic result artifact, exposing `/result`, and moving
the Tool Client and known consumer to run/result.

**Architecture:** Build result artifacts from `ExecutionOutcome` in an
application service, persist them atomically with terminal run state, and
resolve deliverability from application-owned publication state. Keep legacy
routes temporarily alive until the consumer smoke succeeds.

**Tech Stack:** Python 3.11, FastAPI, SQLite WAL, Pydantic, pytest, Docker
Compose.

---

## Delivery Boundary

Included:

- generic canonical `research-report.md` artifact;
- deterministic bounded fallback report;
- `GET /api/runs/{run_id}/result`;
- Tool Client `result --run-id`;
- public Tool Client run/result migration and secret-safe smoke;
- current API and integration documentation.

Deferred unless completed in its own repository:

- private first-party consumer canonical migration and consumer-focused tests.
  Record only command names and pass/fail results in handoff; do not record
  private workspace paths, raw logs, or secrets. Do not claim the final
  first-party consumer gate complete from public repository tests alone.

Excluded:

- removal of legacy task/thread routes or aliases;
- database path/env rename;
- Vue removal;
- dependency cleanup or release tagging.

## File Map

### Create

- `api/run_result_service.py`
- `tests/unit/test_run_result_service.py`
- `tests/integration/test_run_result_api.py`

### Modify

- `agent/run_result.py`
- `api/run_repository.py`
- `api/server.py`
- `api/task_finalizer.py`
- `tools/decision_research_agent_tool.py`
- `tests/unit/test_decision_research_agent_tool.py`
- `tests/integration/test_run_api.py`
- `docs/AGENT_INTEGRATION.md`
- `spec/api-contract.md`
- `spec/data-models.md`
- `spec/state-machine.md`

Private first-party consumer files are changed in their own repository or
workspace and must not be copied into this public repository.

## Task 1: Build Generic Result Artifacts

**Files:**

- Create: `api/run_result_service.py`
- Create: `tests/unit/test_run_result_service.py`
- Modify: `agent/run_result.py`

- [ ] **Step 1: Write artifact RED tests**

```python
def test_generic_report_candidate_builds_canonical_artifact():
    outcome = execution_outcome(
        report_candidate=ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content="# Verified-shaped report",
        )
    )
    result = build_generic_result_artifact(outcome)
    assert result["artifact_id"] == "research-report.md"
    assert result["kind"] == "research_report_markdown"
    assert result["media_type"] == "text/markdown"
    assert result["content"] == "# Verified-shaped report"
    assert result["content_hash"] == hashlib.sha256(
        result["content"].encode("utf-8")
    ).hexdigest()


def test_absent_report_builds_explicit_fallback():
    result = build_generic_result_artifact(
        execution_outcome(report_candidate=None, last_agent_text="partial")
    )
    assert result["kind"] == "research_report_fallback_markdown"
    assert "# Fallback Report" in result["content"]
```

Add tests for empty report, non-canonical virtual path, over-1-MiB content,
absolute-path redaction, deterministic content for a fixed `generated_at`, and
value-free diagnostics.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_run_result_service.py -q
```

- [ ] **Step 3: Implement artifact builder**

Expose:

```python
@dataclass(frozen=True)
class ResolvedRunResult:
    run_id: str
    execution_status: str
    delivery_status: str
    artifact: dict[str, str]


def build_generic_result_artifact(
    outcome: ExecutionOutcome,
    *,
    generated_at: datetime | None = None,
) -> dict[str, str]:
    ...
```

Accept only exact `/workspace/research-report.md`, non-empty UTF-8 text up to
1 MiB. Otherwise build the explicit fallback. Never include a host path.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest tests/unit/test_run_result_service.py -q
git add \
  api/run_result_service.py \
  agent/run_result.py \
  tests/unit/test_run_result_service.py
git commit -m "feat(research): build canonical run results"
```

## Task 2: Persist Generic Artifact Atomically

**Files:**

- Modify: `api/run_repository.py`
- Modify: `api/server.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/unit/test_run_repository.py`

- [ ] **Step 1: Write finalization RED tests**

Assert:

- generic success writes exactly one `research-report.md`;
- artifact and terminal state commit together;
- stale writer writes neither;
- timeout/failure writes no ready result;
- retrying the same fenced finalization does not duplicate artifacts.

The stale-writer test must use two connections against the same WAL database:

```python
first = finalize_run_transaction(
    run_id=run_id,
    segment_id=segment_id,
    expected_state_version=0,
    allowed_previous_statuses={"running"},
    execution_status="completed",
    delivery_status="ready",
    evidence_entries=[],
    artifacts=[artifact],
)
second = finalize_run_transaction(
    run_id=run_id,
    segment_id=segment_id,
    expected_state_version=0,
    allowed_previous_statuses={"running"},
    execution_status="completed",
    delivery_status="ready",
    evidence_entries=[],
    artifacts=[different_artifact],
)
assert first is True
assert second is False
assert stored_artifact_ids(db_path, run_id) == ["research-report.md"]
assert run_state_version(db_path, run_id) == 1
```

This locks the mechanism to the existing
`UPDATE ... WHERE state_version = ? AND execution_status IN (...)` fence and
the surrounding SQLite transaction.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py -q
```

- [ ] **Step 3: Integrate artifact builder**

In `_run_v2_with_persistence`, build generic artifacts before
`finalize_run_transaction`. Pass:

```python
execution_status="completed"
delivery_status="ready"
review_status="not_required"
artifacts=[generic_artifact]
```

Keep Talent artifact/review/publication behavior unchanged.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_run_repository.py \
  tests/integration/test_run_api.py -q
git add api/run_repository.py api/server.py \
  tests/unit/test_run_repository.py tests/integration/test_run_api.py
git commit -m "feat(research): persist canonical generic artifacts"
```

## Task 3: Expose the Canonical Result Endpoint

**Files:**

- Modify: `api/run_result_service.py`
- Modify: `api/server.py`
- Create: `tests/integration/test_run_result_api.py`
- Modify: `spec/api-contract.md`

- [ ] **Step 1: Write endpoint RED tests**

Cover exact mappings:

```text
pending/running -> 409 run_not_terminal
failed -> 409 run_failed
Talent review required -> 409 run_review_required
blocked/rejected -> 409 run_delivery_blocked
missing/corrupt artifact -> 409 run_result_unavailable
unknown run -> 404 run_not_found
ready generic/Talent -> 200 bounded JSON
```

Assert the ready payload contains content but no local path, DB row, review
reason, traceback, or checkpoint metadata.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_run_result_api.py -q
```

- [ ] **Step 3: Implement resolver and route**

The service must select:

- generic: exact `research-report.md`;
- Talent no-review: canonical DecisionBrief Markdown;
- governed Talent: only artifact IDs bound to the current `ready` publication.

Never select by newest timestamp or filename sorting.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_run_result_api.py \
  tests/integration/test_revisioned_review_lifecycle.py -q
git add api/run_result_service.py api/server.py \
  tests/integration/test_run_result_api.py spec/api-contract.md
git commit -m "feat(api): expose canonical run results"
```

## Task 4: Cut the Canonical Tool Client to Run/Result

**Files:**

- Modify: `tools/decision_research_agent_tool.py`
- Modify: `tests/unit/test_decision_research_agent_tool.py`
- Modify: `docs/AGENT_INTEGRATION.md`

- [ ] **Step 1: Write Tool Client RED tests**

Add:

```python
def test_result_requests_canonical_result_endpoint(http_server):
    value = result("run_1", config=http_server.config)
    assert value["artifact"]["artifact_id"] == "research-report.md"
    assert http_server.last_path == "/api/runs/run_1/result"
```

Test `run --wait` polls execution terminal state, then optionally calls result;
bounded HTTP errors preserve server `code/problem/fix`.

- [ ] **Step 2: Run RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_decision_research_agent_tool.py -q
```

- [ ] **Step 3: Implement `result()`**

Add:

```python
def result(run_id: str, config: ToolConfig) -> dict[str, Any]:
    encoded = parse.quote(run_id, safe="")
    return _request_json(
        "GET",
        _join_url(config.base_url, f"/api/runs/{encoded}/result"),
        config=config,
    )
```

Keep legacy commands in this PR. Mark no deprecation behavior beyond existing
compatibility; PR3 deletes them.

- [ ] **Step 4: Run GREEN and commit**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_decision_research_agent_tool.py -q
git add tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py \
  docs/AGENT_INTEGRATION.md
git commit -m "feat(cli): retrieve canonical run results"
```

## Task 5: Migrate and Prove the First-Party Consumer

**Public repository files:** none unless current integration docs require
correction.

- [ ] **Step 1: Rotate the local API key**

Generate and install a replacement without printing it. Do not place it in a
command argument, diff, test fixture, or transcript.

- [ ] **Step 2: Update the known consumer**

Change it to:

```text
repository/tool: decision-research-agent
env: DECISION_RESEARCH_AGENT_URL/API_KEY/TIMEOUT_SECONDS
commands: run -> poll run_id -> result
health service: decision-research-agent only after PR3
```

During PR2 the consumer must tolerate the still-legacy health service value
without using it as routing authority.

- [ ] **Step 3: Run consumer-focused tests**

Use the consumer repository's documented command. Record only pass/fail counts
and command names in the handoff; never copy private paths or secrets into this
repository.

- [ ] **Step 4: Run bounded smoke**

1. start backend with the matching secret;
2. call `/health`;
3. create one bounded generic run;
4. poll by `run_id`;
5. retrieve `/result`;
6. verify result hash/content and no secret in stdout/stderr/logs/diff.

- [ ] **Step 5: Add public-neutral smoke evidence**

Update `docs/AGENT_INTEGRATION.md` with the canonical sequence and state that a
first-party consumer smoke passed. Do not name private workspace paths or
career motivation.

- [ ] **Step 6: Commit documentation, if changed**

```bash
git add docs/AGENT_INTEGRATION.md
git commit -m "docs(api): document canonical run delivery"
```

## PR2 Final Gate

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_run_result_service.py \
  tests/unit/test_run_repository.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_api.py \
  tests/integration/test_revisioned_review_lifecycle.py -q
../../.venv/bin/python -m pytest -q
git diff --check
```

Required manual evidence:

- first-party consumer tests pass, or the private consumer gate is explicitly
  marked deferred;
- bounded run/result smoke passes;
- rotated key is absent from logs, diff, and committed files;
- legacy routes remain temporarily available but are no longer used by
  first-party consumers;
- worktree is clean after commits.
