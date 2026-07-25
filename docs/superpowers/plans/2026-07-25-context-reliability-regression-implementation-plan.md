# Context Reliability Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in one current execution window. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents, create another worktree or branch, or run tasks in parallel.

**Goal:** Add a provider-free paired pytest regression that forces the locked DeepAgents coordinator summarizer in one lane and proves the enumerated application-owned persisted outcome remains equivalent to a non-triggered control lane.

**Architecture:** Keep production behavior unchanged. Add pure public-safe projection and comparison helpers under the existing Agent evaluation namespace, characterize the real native coordinator middleware with a deterministic profiled chat model, and drive two isolated runs through the application-owned create, dispatch, execution, finalization, read, and result-resolution path. Pytest assertions are the only executable authority; the feature creates no CLI, baseline, committed output artifact, or independent CI job.

**Tech Stack:** Python 3.11, pytest, Pydantic-compatible LangChain `BaseChatModel` test doubles, DeepAgents `SummarizationMiddleware`, LangGraph streaming, SQLite application persistence, and the existing DRA Agent evaluation, Evidence, dispatch, artifact, and result-resolution contracts.

---

## Global Constraints

- Implement only the approved design in `docs/superpowers/specs/2026-07-25-context-reliability-regression-design.md`.
- Work serially in the current execution window and current branch. Use `superpowers:executing-plans`; do not use subagent-driven development, parallel lanes, or additional worktrees.
- Modify exactly the seven files in the File And Responsibility Map. If another file appears necessary, stop and request architecture review.
- Do not modify production files under `agent/`, `api/`, or `tools/`; API or database contracts; migrations; dependencies; `.github/workflows/ci.yml`; scenario manifests; committed baselines or reports; top-level `README.md`, `README_CN.md`, or `CHANGELOG.md`; release records; or consumer contracts.
- Do not invoke a provider, external network, Docker, credentials, hosted tracing, or a live user-data path. Fixtures use bounded synthetic text and `https://example.com/context-source`.
- Use the repository-pinned `deepagents==0.6.11`, `langchain==1.3.10`, `langchain-core==1.4.8`, `langgraph==1.2.6`, and `langgraph-checkpoint==4.1.1` environment for implementation verification. Do not change a dependency to make the regression pass.
- Preserve native DeepAgents middleware. Tests may use a profiled fake model and may monkeypatch only `api.server.run_deep_agent` at the application boundary; they must not patch, replace, remove, or reconfigure the native summarizer.
- The control lane must observe zero summary calls. The forced lane must observe a summary call with `lc_source=summarization`, then a coordinator model call whose effective messages contain the native summary message, then the canonical `write_file`.
- The integration path must be real from `create_run` through dispatch claim/start, `_run_dispatched_with_persistence`, `ResearchExecutionService`, citation/artifact finalization, `finalize_run_transaction`, `get_run`, and `resolve_run_result`.
- Any application projection drift, need for a production-file change, inability to trigger native summarization through the locked framework, provider/network/Docker/dependency need, or failure of existing exact sequential deduplication is a RED stop. Return to architecture review; do not loosen equality, remove a projected dimension, create or update a baseline, patch or replace middleware, or alter production behavior.
- Use TDD for each behavior: focused RED, minimal GREEN, focused verification, small refactor only while green, then a semantic atomic commit.
- Do not push, create or update a PR, merge, tag, release, deploy, publish, or clean up a worktree without separate authorization.

## File And Responsibility Map

| File | Responsibility |
|---|---|
| `scripts/agent_evaluation_context.py` | Strict internal projection, hashing, fail-closed validation, resolver normalization, ordered finding codes, and paired comparison |
| `tests/unit/test_agent_evaluation_context.py` | Projection shape, privacy exclusions, Evidence identity validation, resolver success/error normalization, negative controls, and stable finding order |
| `tests/unit/test_deepagents_harness.py` | Real `build_generic_harness()` assembly characterization: one native coordinator summarizer, production fallback no-profile path, and test-only profiled activation |
| `tests/integration/test_context_reliability_regression.py` | Deterministic chat model/harness fixture, control and forced observations, real persisted paired traversal, nested Evidence, exact sequential deduplication, and cache cleanup |
| `tests/unit/test_documentation_contracts.py` | Stable public page title, commands, node names, semantics, limits, stop rules, and docs-index discovery |
| `docs/reference/context-reliability-regression.md` | Operator/developer reference for the pytest-collected pack, commands, diagnosis, code navigation, claims, non-claims, and safe updates |
| `docs/README.md` | One Reference-index entry for the new regression pack |

## Locked Interfaces And Data Shapes

`scripts/agent_evaluation_context.py` will expose only:

```python
CONTEXT_RELIABILITY_FINDING_CODES: tuple[str, ...]

class ContextProjectionError(ValueError):
    code: str

def project_context_reliability_outcome(
    *,
    run: Mapping[str, Any],
    resolution: ResolvedRunResult | RunResultUnavailable,
) -> dict[str, Any]: ...

def compare_context_reliability_outcomes(
    control: Mapping[str, Any],
    forced: Mapping[str, Any],
) -> list[str]: ...
```

The integration helper will call the existing application interfaces with their current signatures:

```python
created = create_run(
    db_path=db_path,
    thread_id=thread_id,
    query=FIXED_QUERY,
)
claim = claim_run_dispatch(
    db_path=db_path,
    worker_id=WORKER_ID,
    lease_seconds=30,
    run_id=created["run_id"],
)
stage = server._RunStage()
origin = server.TerminationOrigin()
checkpoint = server.FinalizationCheckpoint()
task = server.create_tracked_task(
    server._run_dispatched_with_persistence(
        claim,
        db_path=db_path,
        outcome_box=server.OutcomeBox(),
        stage=stage,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    ),
    f"{claim.run_id}:context-reliability:{claim.attempt_count}",
    timeout_seconds=30,
    termination_origin=origin,
    finalization_checkpoint=checkpoint,
)
await task
persisted = get_run(db_path=db_path, run_id=created["run_id"])
resolved = resolve_run_result(db_path=db_path, run_id=created["run_id"])
```

Each lane uses a unique database path, `thread_id`, and generated `run_id`, while keeping the query, tool arguments, source payload, and report bytes identical.

---

### Task 1: Add Fail-Closed Application Projection And Ordered Comparison

**Files:**

- Create: `scripts/agent_evaluation_context.py`
- Create: `tests/unit/test_agent_evaluation_context.py`

- [ ] **Step 1: Write the projection success test**

Create a `_persisted_run()` fixture returning the exact shape consumed from `get_run()` and a real `ResolvedRunResult`:

```python
from copy import deepcopy

import pytest

from api.run_result_service import ResolvedRunResult, RunResultUnavailable
from scripts.agent_evaluation_context import (
    CONTEXT_RELIABILITY_FINDING_CODES,
    ContextProjectionError,
    compare_context_reliability_outcomes,
    project_context_reliability_outcome,
)


RUN_ID = "run_control"
FINGERPRINT = "a" * 64


def _persisted_run(run_id: str = RUN_ID) -> dict:
    return {
        "run_id": run_id,
        "thread_id": f"thread_{run_id}",
        "query": "Compare the fixed synthetic context scenario.",
        "execution_status": "completed",
        "review_status": "not_required",
        "delivery_status": "ready",
        "evidence": [
            {
                "evidence_id": f"ev_{run_id}_{FINGERPRINT}",
                "run_id": run_id,
                "segment_id": f"{run_id}_seg_000",
                "query_text": "Compare the fixed synthetic context scenario.",
                "subagent_name": "network_search",
                "tool_name": "internet_search",
                "source_url": "https://example.com/context-source",
                "source_identity": "https://example.com/context-source",
                "snippet": "Bounded synthetic source content.",
                "evidence_fingerprint": FINGERPRINT,
                "retrieved_at": "2026-07-25T00:00:00+00:00",
                "tool_call_id": "call-search",
                "citation_status": "cited",
                "verification_status": "unverified",
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        ],
        "artifacts": [
            {
                "artifact_id": "research-report.md",
                "kind": "research_report_markdown",
                "media_type": "text/markdown",
                "content_hash": "b" * 64,
                "created_at": "2026-07-25T00:00:00+00:00",
            }
        ],
    }


def _resolved(run_id: str = RUN_ID) -> ResolvedRunResult:
    return ResolvedRunResult(
        run_id=run_id,
        execution_status="completed",
        delivery_status="ready",
        artifact={
            "artifact_id": "research-report.md",
            "kind": "research_report_markdown",
            "media_type": "text/markdown",
            "content": "# Context report\n",
            "content_hash": "b" * 64,
        },
    )


def test_projects_public_safe_application_owned_outcome() -> None:
    projection = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )

    assert list(projection) == [
        "query_sha256",
        "evidence",
        "citation_states",
        "verification_states",
        "artifacts",
        "terminal",
        "resolver",
    ]
    assert projection["evidence"] == [
        {
            "evidence_fingerprint": FINGERPRINT,
            "source_identity_sha256": (
                "8cdc94c2e55df45f640d870fe7bd4a3e4d1371da4fe6f1bdeede230a6aef4a9d"
            ),
            "snippet_sha256": (
                "205037cf11e5846fa027bbb64c6c18cfb980a34f3cdcb00792dca5b8ba40e96a"
            ),
            "query_text_sha256": projection["query_sha256"],
            "subagent_name": "network_search",
            "tool_name": "internet_search",
        }
    ]
    assert projection["resolver"]["kind"] == "success"
    serialized = repr(projection)
    for excluded in (
        RUN_ID,
        "thread_run_control",
        "Compare the fixed synthetic context scenario.",
        "Bounded synthetic source content.",
        "https://example.com/context-source",
        "2026-07-25",
    ):
        assert excluded not in serialized
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py::test_projects_public_safe_application_owned_outcome
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.agent_evaluation_context'`.

- [ ] **Step 3: Implement strict projection helpers**

Create `scripts/agent_evaluation_context.py` with this complete structure and explicit validation:

```python
"""Public-safe paired projections for context-reliability evaluation."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from api.run_result_service import ResolvedRunResult, RunResultUnavailable


_SHA256_RE = re.compile(r"[0-9a-f]{64}\\Z")
CONTEXT_RELIABILITY_FINDING_CODES = (
    "context.query_changed",
    "context.evidence_changed",
    "context.citation_state_changed",
    "context.verification_state_changed",
    "context.artifact_changed",
    "context.terminal_state_changed",
    "context.result_resolution_changed",
)


class ContextProjectionError(ValueError):
    def __init__(self) -> None:
        self.code = "context.projection_invalid"
        super().__init__(self.code)


def _fail() -> None:
    raise ContextProjectionError()


def _text(value: Any) -> str:
    if type(value) is not str or not value:
        _fail()
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_value(value: Any) -> str:
    return _sha256(_text(value))


def _hash64(value: Any) -> str:
    text = _text(value)
    if _SHA256_RE.fullmatch(text) is None:
        _fail()
    return text


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if type(value) is not list or any(not isinstance(item, Mapping) for item in value):
        _fail()
    return value


def _project_evidence(run_id: str, rows: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    projected = []
    seen: set[str] = set()
    for row in rows:
        fingerprint = _hash64(row.get("evidence_fingerprint"))
        if fingerprint in seen:
            _fail()
        seen.add(fingerprint)
        if row.get("evidence_id") != f"ev_{run_id}_{fingerprint}":
            _fail()
        projected.append(
            {
                "evidence_fingerprint": fingerprint,
                "source_identity_sha256": _hash_value(row.get("source_identity")),
                "snippet_sha256": _hash_value(row.get("snippet")),
                "query_text_sha256": _hash_value(row.get("query_text")),
                "subagent_name": _text(row.get("subagent_name")),
                "tool_name": _text(row.get("tool_name")),
            }
        )
    return sorted(projected, key=lambda item: item["evidence_fingerprint"])


def _project_states(
    rows: list[Mapping[str, Any]],
    field: str,
) -> list[dict[str, str]]:
    key = "citation_status" if field == "citation_status" else "verification_status"
    return sorted(
        (
            {
                "evidence_fingerprint": _hash64(row.get("evidence_fingerprint")),
                key: _text(row.get(field)),
            }
            for row in rows
        ),
        key=lambda item: item["evidence_fingerprint"],
    )


def _project_artifacts(rows: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    projected = [
        {
            "artifact_id": _text(row.get("artifact_id")),
            "kind": _text(row.get("kind")),
            "media_type": _text(row.get("media_type")),
            "content_hash": _hash64(row.get("content_hash")),
        }
        for row in rows
    ]
    if len({row["artifact_id"] for row in projected}) != len(projected):
        _fail()
    return sorted(projected, key=lambda item: item["artifact_id"])


def _project_resolver(
    resolution: ResolvedRunResult | RunResultUnavailable,
    *,
    run_id: str,
) -> dict[str, Any]:
    if type(resolution) is ResolvedRunResult:
        if resolution.run_id != run_id:
            _fail()
        artifact = resolution.artifact
        if not isinstance(artifact, Mapping):
            _fail()
        return {
            "kind": "success",
            "execution_status": _text(resolution.execution_status),
            "delivery_status": _text(resolution.delivery_status),
            "artifact_id": _text(artifact.get("artifact_id")),
            "artifact_kind": _text(artifact.get("kind")),
            "artifact_media_type": _text(artifact.get("media_type")),
            "artifact_content_hash": _hash64(artifact.get("content_hash")),
        }
    if type(resolution) is RunResultUnavailable:
        if type(resolution.status_code) is not int or type(resolution.code) is not str:
            _fail()
        return {
            "kind": "error",
            "status_code": resolution.status_code,
            "code": resolution.code,
            "retryable": resolution.status_code == 409,
        }
    _fail()


def project_context_reliability_outcome(
    *,
    run: Mapping[str, Any],
    resolution: ResolvedRunResult | RunResultUnavailable,
) -> dict[str, Any]:
    if not isinstance(run, Mapping):
        _fail()
    run_id = _text(run.get("run_id"))
    query_sha256 = _hash_value(run.get("query"))
    evidence = _rows(run.get("evidence"))
    projection = {
        "query_sha256": query_sha256,
        "evidence": _project_evidence(run_id, evidence),
        "citation_states": _project_states(evidence, "citation_status"),
        "verification_states": _project_states(evidence, "verification_status"),
        "artifacts": _project_artifacts(_rows(run.get("artifacts"))),
        "terminal": {
            "execution_status": _text(run.get("execution_status")),
            "review_status": _text(run.get("review_status")),
            "delivery_status": _text(run.get("delivery_status")),
        },
        "resolver": _project_resolver(resolution, run_id=run_id),
    }
    if any(row["query_text_sha256"] != query_sha256 for row in projection["evidence"]):
        _fail()
    return projection


def compare_context_reliability_outcomes(
    control: Mapping[str, Any],
    forced: Mapping[str, Any],
) -> list[str]:
    if not isinstance(control, Mapping) or not isinstance(forced, Mapping):
        _fail()
    comparisons = (
        ("query_sha256", "context.query_changed"),
        ("evidence", "context.evidence_changed"),
        ("citation_states", "context.citation_state_changed"),
        ("verification_states", "context.verification_state_changed"),
        ("artifacts", "context.artifact_changed"),
        ("terminal", "context.terminal_state_changed"),
        ("resolver", "context.result_resolution_changed"),
    )
    if set(control) != {item[0] for item in comparisons} or set(forced) != set(control):
        _fail()
    return [code for field, code in comparisons if control[field] != forced[field]]
```

- [ ] **Step 4: Run the success test and make only type-level corrections**

Run the Step 2 command.

Expected: PASS. If a constructor or field type differs from the locked environment, correct the test or annotation to match the actual imported type without changing the projection contract.

- [ ] **Step 5: Add fail-closed and resolver-error tests**

Add exact tests for invalid Evidence identity, invalid hash, raw mappings instead of resolver types, and normalized resolver errors:

```python
@pytest.mark.parametrize(
    ("mutate",),
    [
        (lambda run: run["evidence"][0].__setitem__("evidence_id", "ev_foreign"),),
        (lambda run: run["evidence"][0].__setitem__("evidence_fingerprint", "bad"),),
        (lambda run: run["evidence"][0].__setitem__("query_text", "different"),),
        (lambda run: run.__setitem__("artifacts", "not-a-list"),),
    ],
    ids=("foreign-evidence-id", "invalid-fingerprint", "query-mismatch", "invalid-artifacts"),
)
def test_projection_fails_closed_without_raw_details(mutate) -> None:
    run = _persisted_run()
    mutate(run)
    with pytest.raises(ContextProjectionError) as raised:
        project_context_reliability_outcome(run=run, resolution=_resolved())
    assert raised.value.code == "context.projection_invalid"
    assert str(raised.value) == "context.projection_invalid"


def test_projects_resolver_error_without_problem_or_fix() -> None:
    error = RunResultUnavailable(
        status_code=409,
        code="run_not_terminal",
        problem="private diagnostic",
        fix="private recovery",
    )
    projection = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=error,
    )
    assert projection["resolver"] == {
        "kind": "error",
        "status_code": 409,
        "code": "run_not_terminal",
        "retryable": True,
    }
    assert "private diagnostic" not in repr(projection)
    assert "private recovery" not in repr(projection)


def test_projection_rejects_mismatched_resolver_run_id() -> None:
    with pytest.raises(ContextProjectionError, match="context.projection_invalid"):
        project_context_reliability_outcome(
            run=_persisted_run("run_control"),
            resolution=_resolved("run_foreign"),
        )


def test_projection_rejects_raw_mapping_as_resolution() -> None:
    with pytest.raises(ContextProjectionError, match="context.projection_invalid"):
        project_context_reliability_outcome(
            run=_persisted_run(),
            resolution={
                "run_id": RUN_ID,
                "execution_status": "completed",
                "delivery_status": "ready",
            },
        )


def test_run_local_identities_are_validated_then_excluded_from_equality() -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run("run_control"),
        resolution=_resolved("run_control"),
    )
    forced = project_context_reliability_outcome(
        run=_persisted_run("run_forced"),
        resolution=_resolved("run_forced"),
    )
    assert control == forced
    assert compare_context_reliability_outcomes(control, forced) == []
```

- [ ] **Step 6: Add all negative controls and stable multi-finding order**

Use parameterized mutations against a deep copy of the control projection:

```python
def _set_nested(projection: dict, path: tuple, value) -> None:
    target = projection
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("query_sha256",), "c" * 64, "context.query_changed"),
        (("evidence", 0, "evidence_fingerprint"), "c" * 64, "context.evidence_changed"),
        (("citation_states", 0, "citation_status"), "uncited", "context.citation_state_changed"),
        (("verification_states", 0, "verification_status"), "verified", "context.verification_state_changed"),
        (("artifacts", 0, "content_hash"), "c" * 64, "context.artifact_changed"),
        (("terminal", "delivery_status"), "blocked", "context.terminal_state_changed"),
        (("resolver", "artifact_content_hash"), "c" * 64, "context.result_resolution_changed"),
    ],
    ids=(
        "query-hash",
        "evidence-fingerprint",
        "citation-status",
        "verification-status",
        "artifact-content-hash",
        "delivery-status",
        "resolver-artifact-hash",
    ),
)
def test_comparison_emits_dimension_specific_finding(path, value, expected) -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )
    forced = deepcopy(control)
    _set_nested(forced, path, value)
    assert compare_context_reliability_outcomes(control, forced) == [expected]


def test_comparison_uses_stable_finding_order() -> None:
    control = project_context_reliability_outcome(
        run=_persisted_run(),
        resolution=_resolved(),
    )
    forced = deepcopy(control)
    forced["query_sha256"] = "c" * 64
    forced["terminal"]["delivery_status"] = "blocked"
    forced["resolver"]["artifact_content_hash"] = "d" * 64
    assert compare_context_reliability_outcomes(control, forced) == [
        "context.query_changed",
        "context.terminal_state_changed",
        "context.result_resolution_changed",
    ]
    assert CONTEXT_RELIABILITY_FINDING_CODES == (
        "context.query_changed",
        "context.evidence_changed",
        "context.citation_state_changed",
        "context.verification_state_changed",
        "context.artifact_changed",
        "context.terminal_state_changed",
        "context.result_resolution_changed",
    )
```

- [ ] **Step 7: Run the complete projection unit module**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_agent_evaluation_context.py
```

Expected: PASS with every test in the module passing.

- [ ] **Step 8: Refactor only duplication and rerun**

If fixture setup or hash construction is duplicated, extract only local test helpers. Do not add schemas, CLI behavior, serialization, or files. Rerun the Step 7 command and expect PASS.

- [ ] **Step 9: Commit the projection slice**

```bash
git add \
  scripts/agent_evaluation_context.py \
  tests/unit/test_agent_evaluation_context.py
git commit -m "test(context): add persisted outcome projection"
```

---

### Task 2: Characterize The Locked Native Coordinator Summarizer

**Files:**

- Modify: `tests/unit/test_deepagents_harness.py`

- [ ] **Step 1: Add a profiled deterministic model fixture**

Add imports for `Any`, `Sequence`, `BaseChatModel`, `BaseMessage`, `AIMessage`, `ChatGeneration`, `ChatResult`, and `Field`, then add:

```python
class ProfiledHarnessModel(BaseChatModel):
    profile: dict[str, Any] | None = {"max_input_tokens": 256}
    bound_tool_names: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "profiled-context-harness-model"

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        del tool_choice, kwargs
        self.bound_tool_names = [
            getattr(tool, "name", "")
            if not isinstance(tool, dict)
            else str(tool.get("name", ""))
            for tool in tools
        ]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="done"))]
        )
```

- [ ] **Step 2: Write the structural RED test**

Extend `_capture_framework_assembly()` to keep `captured["middleware"]` from the real coordinator assembly and add:

```python
def test_locked_native_summarizer_profile_forces_coordinator_summary(
    monkeypatch,
) -> None:
    from deepagents.middleware.summarization import SummarizationMiddleware

    from agent.deepagents_harness import build_generic_harness
    from agent.llm import FallbackChatModel
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    captured = _capture_framework_assembly(monkeypatch)
    profiled = ProfiledHarnessModel()
    build_generic_harness(model=profiled)
    summarizers = [
        item
        for item in captured["middleware"]
        if isinstance(item, SummarizationMiddleware)
    ]
    assert len(summarizers) == 1
    assert summarizers[0].model is profiled
    assert summarizers[0].trigger == ("fraction", 0.85)
    assert summarizers[0].keep == ("fraction", 0.10)

    production_wrapper = FallbackChatModel(
        primary=FakeListChatModel(responses=["primary"]),
        fallback=FakeListChatModel(responses=["fallback"]),
    )
    assert getattr(production_wrapper, "profile", None) is None

    captured.clear()
    build_generic_harness(model=production_wrapper)
    production_summarizer = next(
        item
        for item in captured["middleware"]
        if isinstance(item, SummarizationMiddleware)
    )
    assert production_summarizer.trigger == ("tokens", 170000)
    assert production_summarizer.keep == ("messages", 6)
```

This test reads configuration from the real `build_generic_harness()` path. It does not instantiate or substitute a summarization middleware.

- [ ] **Step 3: Run the structural node and confirm RED or locked compatibility**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary
```

Expected before import/type corrections: FAIL at the first mismatch between the planned test double and the locked `BaseChatModel`/DeepAgents API. Expected after corrections: PASS with exactly one native summarizer and both native default paths characterized.

- [ ] **Step 4: Correct only locked API signatures**

If the locked `SummarizationMiddleware` public alias or model `profile` field requires a narrower annotation, inspect the installed pinned source and correct only the imports/annotations/constructor. Preserve these assertions:

```python
assert len(summarizers) == 1
assert summarizers[0].model is profiled
assert summarizers[0].trigger == ("fraction", 0.85)
assert summarizers[0].keep == ("fraction", 0.10)
assert getattr(production_wrapper, "profile", None) is None
assert production_summarizer.trigger == ("tokens", 170000)
assert production_summarizer.keep == ("messages", 6)
```

If the locked version does not expose these native values, stop for architecture review rather than replacing middleware or weakening the assertions.

- [ ] **Step 5: Run the focused node and existing middleware-stack test**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_deepagents_harness.py::test_pinned_deepagents_middleware_stack_and_subagents \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary
```

Expected: both nodes PASS.

- [ ] **Step 6: Commit the compatibility characterization**

```bash
git add tests/unit/test_deepagents_harness.py
git commit -m "test(context): characterize native summarizer profile"
```

---

### Task 3: Build Deterministic Control And Forced Harness Lanes

**Files:**

- Create: `tests/integration/test_context_reliability_regression.py`

- [ ] **Step 1: Add fixed inputs and the recording model skeleton**

Create the integration module with these constants and one model used by both coordinator and compiled researcher calls:

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.harness_contracts import ReportCandidate
from api.research_execution_service import ResearchExecutionService
from scripts.agent_evaluation_context import (
    compare_context_reliability_outcomes,
    project_context_reliability_outcome,
)


FIXED_QUERY = "Compare the fixed synthetic context reliability scenario."
PRE_SUMMARY_SEARCH_QUERY = "fixed context source"
POST_SUMMARY_SEARCH_QUERY = "fixed post-summary context source"
SOURCE_URL = "https://example.com/context-source"
SOURCE_CONTENT = "Bounded synthetic source content."
REPORT_CONTENT = f"# Context report\\n\\nSource: {SOURCE_URL}\\n"
LARGE_TASK_RESULT = "Research complete. " + ("synthetic-context " * 800)
SECOND_TASK_RESULT = "Post-summary duplicate search complete."
CONTROL_MAX_INPUT_TOKENS = 32768
FORCED_MAX_INPUT_TOKENS = 512
WORKER_ID = "dispatch_worker_0000000000000000000000000000000c"


@dataclass
class ContextCallRecorder:
    coordinator_calls: int = 0
    researcher_calls: int = 0
    summary_calls: int = 0
    events: list[str] = field(default_factory=list)
    effective_message_sources: list[list[str | None]] = field(default_factory=list)
    task_args: list[dict[str, str]] = field(default_factory=list)
    task_results: list[str] = field(default_factory=list)
    search_tool_emissions: list[str] = field(default_factory=list)
    search_payloads: list[bytes] = field(default_factory=list)


class ScriptedContextReliabilityModel(BaseChatModel):
    profile: dict[str, Any] | None = None
    recorder: ContextCallRecorder
    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "scripted-context-reliability-model"

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        del tool_choice, kwargs
        names = tuple(
            getattr(tool, "name", "")
            if not isinstance(tool, dict)
            else str(tool.get("name", ""))
            for tool in tools
        )
        return self.model_copy(update={"bound_tool_names": names})

    def _is_summary_call(self, run_manager) -> bool:
        metadata = getattr(run_manager, "metadata", {}) or {}
        return metadata.get("lc_source") == "summarization"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, kwargs
        if self._is_summary_call(run_manager):
            self.recorder.summary_calls += 1
            self.recorder.events.append("summary")
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="Bounded native summary."))
                ]
            )

        if "internet_search" in self.bound_tool_names and "task" not in self.bound_tool_names:
            self.recorder.researcher_calls += 1
            if self.recorder.researcher_calls == 1:
                self.recorder.events.append("pre_search_tool_emission")
                self.recorder.search_tool_emissions.append(PRE_SUMMARY_SEARCH_QUERY)
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "internet_search",
                            "args": {"query": PRE_SUMMARY_SEARCH_QUERY},
                            "id": "call-pre-summary-search",
                            "type": "tool_call",
                        }
                    ],
                )
            elif self.recorder.researcher_calls == 2:
                self.recorder.events.append("large_task_result")
                self.recorder.task_results.append(LARGE_TASK_RESULT)
                message = AIMessage(content=LARGE_TASK_RESULT)
            elif self.recorder.researcher_calls in {3, 4}:
                emission = self.recorder.researcher_calls - 2
                self.recorder.events.append(f"post_search_tool_emission_{emission}")
                self.recorder.search_tool_emissions.append(
                    POST_SUMMARY_SEARCH_QUERY
                )
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "internet_search",
                            "args": {"query": POST_SUMMARY_SEARCH_QUERY},
                            "id": f"call-post-summary-search-{emission}",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                self.recorder.events.append("post_summary_provider_once_observed")
                self.recorder.events.append("second_task_result")
                self.recorder.task_results.append(SECOND_TASK_RESULT)
                message = AIMessage(content=SECOND_TASK_RESULT)
            return ChatResult(generations=[ChatGeneration(message=message)])

        self.recorder.coordinator_calls += 1
        self.recorder.effective_message_sources.append(
            [
                message.additional_kwargs.get("lc_source")
                for message in messages
                if isinstance(message, HumanMessage)
            ]
        )
        if self.recorder.coordinator_calls == 1:
            task_args = {
                "description": "Run the pre-summary fixed synthetic search.",
                "subagent_type": "network_search",
            }
            self.recorder.task_args.append(task_args)
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": task_args,
                        "id": "call-pre-summary-task",
                        "type": "tool_call",
                    }
                ],
            )
        elif self.recorder.coordinator_calls == 2:
            if any(
                isinstance(item, HumanMessage)
                and item.additional_kwargs.get("lc_source") == "summarization"
                for item in messages
            ):
                self.recorder.events.append("coordinator_after_summary")
            task_args = {
                "description": "Run two exact sequential post-summary searches.",
                "subagent_type": "network_search",
            }
            self.recorder.task_args.append(task_args)
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": task_args,
                        "id": "call-post-summary-task",
                        "type": "tool_call",
                    }
                ],
            )
        elif not any(
            isinstance(item, ToolMessage) and item.name == "write_file"
            for item in messages
        ):
            assert self.recorder.task_results == [
                LARGE_TASK_RESULT,
                SECOND_TASK_RESULT,
            ]
            self.recorder.events.append("write_file")
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/workspace/research-report.md",
                            "content": REPORT_CONTENT,
                        },
                        "id": "call-write-report",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="Context report written.")
        return ChatResult(generations=[ChatGeneration(message=message)])
```

- [ ] **Step 2: Add the real harness builder with one fake search boundary**

Use the real `build_generic_harness()` and monkeypatch only the provider-facing `_internet_search_impl`; the real `internet_search` tool and `search_with_dedup()` remain in the execution path:

```python
def _build_lane_harness(monkeypatch, *, forced: bool):
    import tools.tavily_tools as tavily_tools

    calls: list[tuple[str, dict[str, Any]]] = []
    recorder = ContextCallRecorder()
    model = ScriptedContextReliabilityModel(
        profile={
            "max_input_tokens": (
                FORCED_MAX_INPUT_TOKENS
                if forced
                else CONTROL_MAX_INPUT_TOKENS
            )
        },
        recorder=recorder,
    )

    def fake_search(query: str, **kwargs: Any) -> str:
        calls.append((query, dict(kwargs)))
        payload = json.dumps(
            {"results": [{"url": SOURCE_URL, "content": SOURCE_CONTENT}]},
            sort_keys=True,
        )
        recorder.search_payloads.append(payload.encode("utf-8"))
        return payload

    monkeypatch.setattr(tavily_tools, "_internet_search_impl", fake_search)
    from agent.deepagents_harness import build_generic_harness

    return build_generic_harness(model=model), recorder, calls
```

`tools.tavily_tools.internet_search()` reads `get_run_context()` and calls `search_with_dedup(query, search_fn=_internet_search_impl, thread_id=run_id, max_results=5, topic="general", include_raw_content=False)`. The monkeypatch therefore replaces only the network/provider leaf while preserving the real run-scoped cache and tool contract.

- [ ] **Step 3: Write the control-versus-forced observation test**

```python
@pytest.mark.asyncio
async def test_control_and_forced_lanes_observe_native_summary_only_when_forced(
    tmp_path,
    monkeypatch,
) -> None:
    observations = {}
    for forced in (False, True):
        harness, recorder, search_calls = _build_lane_harness(
            monkeypatch,
            forced=forced,
        )
        service = ResearchExecutionService(
            harness=harness,
            project_root=tmp_path / ("forced" if forced else "control"),
        )
        outcome = await service.execute(
            FIXED_QUERY,
            f"thread-{'forced' if forced else 'control'}",
            run_id=f"run-{'forced' if forced else 'control'}",
            segment_id=f"segment-{'forced' if forced else 'control'}",
            profile_id="generic",
        )
        observations[forced] = (
            FIXED_QUERY.encode("utf-8"),
            recorder,
            outcome,
            search_calls,
        )

    control_query, control_recorder, control_outcome, control_search_calls = (
        observations[False]
    )
    forced_query, forced_recorder, forced_outcome, forced_search_calls = (
        observations[True]
    )
    assert control_query == forced_query == FIXED_QUERY.encode("utf-8")
    assert control_recorder.summary_calls == 0
    assert forced_recorder.summary_calls == 1
    expected_task_args = [
        {
            "description": "Run the pre-summary fixed synthetic search.",
            "subagent_type": "network_search",
        },
        {
            "description": "Run two exact sequential post-summary searches.",
            "subagent_type": "network_search",
        },
    ]
    expected_search_calls = [
        (
            PRE_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        ),
        (
            POST_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        ),
    ]
    assert control_recorder.task_args == forced_recorder.task_args == (
        expected_task_args
    )
    assert control_recorder.task_results == forced_recorder.task_results == [
        LARGE_TASK_RESULT,
        SECOND_TASK_RESULT,
    ]
    assert control_recorder.search_tool_emissions == (
        forced_recorder.search_tool_emissions
    ) == [
        PRE_SUMMARY_SEARCH_QUERY,
        POST_SUMMARY_SEARCH_QUERY,
        POST_SUMMARY_SEARCH_QUERY,
    ]
    assert control_recorder.search_payloads == forced_recorder.search_payloads
    assert control_search_calls == forced_search_calls == expected_search_calls
    required_forced_order = [
        "pre_search_tool_emission",
        "large_task_result",
        "summary",
        "coordinator_after_summary",
        "post_search_tool_emission_1",
        "post_search_tool_emission_2",
        "post_summary_provider_once_observed",
        "second_task_result",
        "write_file",
    ]
    assert [event for event in forced_recorder.events if event in required_forced_order] == (
        required_forced_order
    )
    assert "summary" not in control_recorder.events
    assert "coordinator_after_summary" not in control_recorder.events
    assert any(
        "summarization" in sources
        for sources in forced_recorder.effective_message_sources
    )
    assert control_outcome.report_candidate == forced_outcome.report_candidate == (
        ReportCandidate(
            path=PurePosixPath("/workspace/research-report.md"),
            content=REPORT_CONTENT,
        )
    )
```

- [ ] **Step 4: Run the observation node and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/integration/test_context_reliability_regression.py::test_control_and_forced_lanes_observe_native_summary_only_when_forced
```

Expected: FAIL until the locked model callback metadata, model routing, tool construction, and bounded payload cross the native fractional threshold.

- [ ] **Step 5: Tune only the test profile and bounded payload**

Both lanes must retain the byte-identical `FIXED_QUERY`, task descriptions and arguments, fake-search payload, `LARGE_TASK_RESULT`, `SECOND_TASK_RESULT`, and `REPORT_CONTENT`. Tune only the two test-only profile values and, if necessary, the one common bounded payload used by both lanes:

```python
CONTROL_MAX_INPUT_TOKENS = 32768
FORCED_MAX_INPUT_TOKENS = 512
LARGE_TASK_RESULT = "Research complete. " + ("synthetic-context " * 800)
```

The only per-lane input difference is `profile.max_input_tokens`: the larger control profile keeps the common scenario below its native threshold, while the smaller forced profile crosses its native threshold. Do not add forced-only padding, change either lane’s scripted trajectory, change production configuration, or replace/patch middleware. Re-run Step 4 until PASS with exactly one forced summary event.

If the native coordinator summarizer cannot be triggered without middleware patching/replacement, stop and return to architecture review.

- [ ] **Step 6: Commit the deterministic lane fixture**

```bash
git add tests/integration/test_context_reliability_regression.py
git commit -m "test(context): observe native summary lanes"
```

---

### Task 4: Traverse Real Persistence And Compare Paired Outcomes

**Files:**

- Modify: `tests/integration/test_context_reliability_regression.py`

- [ ] **Step 1: Add the real lane runner**

Add imports for `api.server`, `create_run`, `get_run`, `claim_run_dispatch`, and `resolve_run_result`, then implement:

```python
async def _run_persisted_lane(
    *,
    db_path: str,
    thread_id: str,
    harness,
    monkeypatch,
    project_root,
):
    import api.server as server
    from api.run_dispatch_repository import claim_run_dispatch
    from api.run_repository import create_run, get_run
    from api.run_result_service import resolve_run_result

    service = ResearchExecutionService(
        harness=harness,
        project_root=project_root,
    )

    async def test_adapter(query: str, persisted_thread_id: str, **kwargs):
        return await service.execute(
            query,
            persisted_thread_id,
            run_id=kwargs["run_id"],
            segment_id=kwargs["segment_id"],
            outcome_box=kwargs["outcome_box"],
            profile_id=kwargs["profile_id"],
            scope=kwargs["scope"],
        )

    monkeypatch.setattr(server, "run_deep_agent", test_adapter)
    created = create_run(
        db_path=db_path,
        thread_id=thread_id,
        query=FIXED_QUERY,
    )
    claim = claim_run_dispatch(
        db_path=db_path,
        worker_id=WORKER_ID,
        lease_seconds=30,
        run_id=created["run_id"],
    )
    assert claim is not None
    stage = server._RunStage()
    origin = server.TerminationOrigin()
    checkpoint = server.FinalizationCheckpoint()
    task = server.create_tracked_task(
        server._run_dispatched_with_persistence(
            claim,
            db_path=db_path,
            outcome_box=server.OutcomeBox(),
            stage=stage,
            termination_origin=origin,
            finalization_checkpoint=checkpoint,
        ),
        f"{claim.run_id}:context-reliability:{claim.attempt_count}",
        timeout_seconds=30,
        termination_origin=origin,
        finalization_checkpoint=checkpoint,
    )
    await task
    persisted = get_run(db_path=db_path, run_id=created["run_id"])
    assert persisted is not None
    resolved = resolve_run_result(
        db_path=db_path,
        run_id=created["run_id"],
    )
    return created, persisted, resolved
```

This is the only allowed monkeypatch of an application runtime boundary. All persistence, start fencing, finalization, result reads, and cache cleanup remain real.

- [ ] **Step 2: Write the paired persisted equivalence test**

```python
@pytest.mark.asyncio
async def test_paired_persisted_application_outcomes_remain_equivalent(
    tmp_path,
    monkeypatch,
) -> None:
    from tools.tavily_tools import _search_cache

    lane_results = {}
    lane_recorders = {}
    for forced in (False, True):
        lane_name = "forced" if forced else "control"
        lane_db_path = str(tmp_path / f"{lane_name}.db")
        harness, recorder, _ = _build_lane_harness(monkeypatch, forced=forced)
        created, persisted, resolved = await _run_persisted_lane(
            db_path=lane_db_path,
            thread_id=f"thread-{lane_name}",
            harness=harness,
            monkeypatch=monkeypatch,
            project_root=tmp_path / lane_name,
        )
        lane_recorders[forced] = recorder
        assert persisted["state_version"] == 2
        assert persisted["segments"][0]["status"] == "completed"
        assert persisted["failure_cause"] is None
        assert persisted["execution_status"] == "completed"
        assert persisted["review_status"] == "not_required"
        assert persisted["delivery_status"] == "ready"
        assert _dispatch_status(lane_db_path, created["run_id"]) == "started"
        assert [item["artifact_id"] for item in persisted["artifacts"]] == [
            "research-report.md"
        ]
        lane_results[forced] = project_context_reliability_outcome(
            run=persisted,
            resolution=resolved,
        )
        assert created["run_id"] not in _search_cache

    assert lane_recorders[False].summary_calls == 0
    assert lane_recorders[True].summary_calls == 1
    assert compare_context_reliability_outcomes(
        lane_results[False],
        lane_results[True],
    ) == []
```

- [ ] **Step 3: Add explicit dispatch-start persistence assertion**

Read the lane database after traversal:

```python
import sqlite3


def _dispatch_status(db_path: str, run_id: str) -> str:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT status FROM run_dispatches_v1 WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row[0]
```

The complete paired-loop snippet above defines `lane_db_path`, passes that exact path to `_run_persisted_lane()`, and uses it for the dispatch assertion:

```python
lane_db_path = str(tmp_path / f"{lane_name}.db")
created, persisted, resolved = await _run_persisted_lane(
    db_path=lane_db_path,
    thread_id=f"thread-{lane_name}",
    harness=harness,
    monkeypatch=monkeypatch,
    project_root=tmp_path / lane_name,
)
assert _dispatch_status(lane_db_path, created["run_id"]) == "started"
```

- [ ] **Step 4: Run the paired persistence node and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/integration/test_context_reliability_regression.py::test_paired_persisted_application_outcomes_remain_equivalent
```

Expected: FAIL at any real traversal, Evidence, citation, artifact, terminal, resolver, or projection mismatch. Treat a non-empty finding list as a RED stop requiring architecture review.

- [ ] **Step 5: Make only fixture-level deterministic corrections**

Permitted corrections are limited to deterministic test model routing, test IDs, the common bounded payload shared byte-for-byte by both lanes, the two lane profile limits, fake search payload, and canonical report content. Do not add a lane-specific trajectory or normalize away an application difference in `project_context_reliability_outcome()`.

Re-run Step 4. Expected: PASS with an empty finding list.

- [ ] **Step 6: Commit the persisted paired regression**

```bash
git add tests/integration/test_context_reliability_regression.py
git commit -m "test(context): compare persisted summary outcomes"
```

---

### Task 5: Lock Nested Evidence, Exact Sequential Deduplication, And Cleanup

**Files:**

- Modify: `tests/integration/test_context_reliability_regression.py`

- [ ] **Step 1: Record ordering at the nested search boundary**

The first task emits one pre-summary search and then the same URL-free large coordinator-facing result in both lanes. The second task begins only after coordinator call 2, emits two exact sequential post-summary searches, then returns a small result:

```python
assert SOURCE_URL not in LARGE_TASK_RESULT
assert recorder.task_results == [LARGE_TASK_RESULT, SECOND_TASK_RESULT]
assert recorder.search_tool_emissions == [
    PRE_SUMMARY_SEARCH_QUERY,
    POST_SUMMARY_SEARCH_QUERY,
    POST_SUMMARY_SEARCH_QUERY,
]
```

In the forced observation, filter the recorder to the required markers and assert the complete order:

```python
required_forced_order = [
    "pre_search_tool_emission",
    "large_task_result",
    "summary",
    "coordinator_after_summary",
    "post_search_tool_emission_1",
    "post_search_tool_emission_2",
    "post_summary_provider_once_observed",
    "second_task_result",
    "write_file",
]
assert [event for event in recorder.events if event in required_forced_order] == (
    required_forced_order
)
```

The two post-summary tool-call emissions are recorder events from the model boundary. `post_summary_provider_once_observed` is appended only after both ToolMessages have returned, while the separate `search_calls` list records actual invocations of the fake provider leaf. This keeps model/tool emissions distinct from underlying provider calls.

- [ ] **Step 2: Add nested Evidence assertions to the persisted test**

For each persisted lane assert one retained semantic Evidence row. Both distinct queries return the same synthetic source identity and content, so the existing Evidence ledger deduplicates them by fingerprint:

```python
assert len(persisted["evidence"]) == 1
evidence = persisted["evidence"][0]
assert evidence["evidence_id"] == (
    f"ev_{created['run_id']}_{evidence['evidence_fingerprint']}"
)
assert evidence["subagent_name"] == "network_search"
assert evidence["tool_name"] == "internet_search"
assert evidence["source_url"] == SOURCE_URL
assert evidence["snippet"] == SOURCE_CONTENT
assert evidence["citation_status"] == "cited"
assert evidence["verification_status"] == "unverified"
```

This proves nested `internet_search` Evidence reaches the application ledger even though both coordinator-facing task results omit the URL. The second distinct query returns the same semantic source, and the repeated post-summary call is also served from the search cache, so neither creates an additional Evidence fingerprint.

- [ ] **Step 3: Lock the post-summary sequential dedup assertions**

The researcher skeleton from Task 3 already emits the post-summary query on calls 3 and 4, with the second call emitted only after the first ToolMessage returns. Assert the two model/tool emissions independently from underlying fake-provider calls:

```python
assert recorder.search_tool_emissions.count(POST_SUMMARY_SEARCH_QUERY) == 2
assert [query for query, _ in search_calls].count(POST_SUMMARY_SEARCH_QUERY) == 1
```

Do not emit parallel duplicate tool calls. Do not collapse the two model/tool emissions merely because the real run-scoped cache collapses the provider leaf invocation.

- [ ] **Step 4: Assert exact deduplication and run-cache cleanup**

Return the underlying fake-search call list from `_build_lane_harness()` and add the third stable integration node:

```python
@pytest.mark.asyncio
async def test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache(
    tmp_path,
    monkeypatch,
) -> None:
    from tools.tavily_tools import _search_cache

    db_path = str(tmp_path / "forced-evidence.db")
    harness, recorder, search_calls = _build_lane_harness(
        monkeypatch,
        forced=True,
    )
    created, persisted, _ = await _run_persisted_lane(
        db_path=db_path,
        thread_id="thread-forced-evidence",
        harness=harness,
        monkeypatch=monkeypatch,
        project_root=tmp_path / "forced-evidence",
    )

    required_forced_order = [
        "pre_search_tool_emission",
        "large_task_result",
        "summary",
        "coordinator_after_summary",
        "post_search_tool_emission_1",
        "post_search_tool_emission_2",
        "post_summary_provider_once_observed",
        "second_task_result",
        "write_file",
    ]
    assert [event for event in recorder.events if event in required_forced_order] == (
        required_forced_order
    )
    assert recorder.search_tool_emissions.count(POST_SUMMARY_SEARCH_QUERY) == 2
    assert search_calls == [
        (
            PRE_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        ),
        (
            POST_SUMMARY_SEARCH_QUERY,
            {
                "max_results": 5,
                "topic": "general",
                "include_raw_content": False,
            },
        )
    ]
    assert [query for query, _ in search_calls].count(
        POST_SUMMARY_SEARCH_QUERY
    ) == 1
    assert len(persisted["evidence"]) == 1
    evidence = persisted["evidence"][0]
    assert evidence["evidence_id"] == (
        f"ev_{created['run_id']}_{evidence['evidence_fingerprint']}"
    )
    assert evidence["subagent_name"] == "network_search"
    assert evidence["tool_name"] == "internet_search"
    assert evidence["source_url"] == SOURCE_URL
    assert evidence["snippet"] == SOURCE_CONTENT
    assert evidence["citation_status"] == "cited"
    assert evidence["verification_status"] == "unverified"
    assert created["run_id"] not in _search_cache
```

Also keep the same cache-absence assertion in each paired lane after its own `ResearchExecutionService.execute()` returns:

```python
assert created["run_id"] not in _search_cache
```

Also assert the other lane’s run ID is absent after its own service returns. Do not assert semantic, concurrent, delegation-level, or global deduplication.

- [ ] **Step 5: Run the three stable integration nodes**

The module must expose these behavior-named nodes:

```text
test_control_and_forced_lanes_observe_native_summary_only_when_forced
test_paired_persisted_application_outcomes_remain_equivalent
test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache
```

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/integration/test_context_reliability_regression.py
```

Expected: all three nodes PASS. If exact sequential deduplication or cleanup fails outside the existing `query + kwargs` and run-scoped contract, stop for architecture review.

- [ ] **Step 6: Refactor shared lane setup while green**

Extract only `_LaneObservation` as a frozen dataclass if returning tuples becomes ambiguous:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class _LaneObservation:
    created: dict[str, str]
    persisted: dict[str, Any]
    resolved: Any
    recorder: ContextCallRecorder
    search_calls: list[tuple[str, dict[str, Any]]]
```

Keep all fixtures in the integration module. Rerun Step 5 and expect PASS.

- [ ] **Step 7: Commit Evidence and cache coverage**

```bash
git add tests/integration/test_context_reliability_regression.py
git commit -m "test(context): lock evidence and cache cleanup"
```

---

### Task 6: Add The Public Pytest-Pack Reference And Documentation Contract

**Files:**

- Modify: `tests/unit/test_documentation_contracts.py`
- Create: `docs/reference/context-reliability-regression.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Write the failing documentation contract**

Append:

```python
def test_context_reliability_pytest_pack_is_documented_and_indexed() -> None:
    reference = (
        PROJECT_ROOT / "docs/reference/context-reliability-regression.md"
    ).read_text(encoding="utf-8")
    docs_index = (PROJECT_ROOT / "docs/README.md").read_text(encoding="utf-8")
    collapsed = _collapsed(reference)

    assert reference.startswith("# Context Reliability Pytest Regression Pack\\n")
    for phrase in (
        "pytest-collected regression pack",
        "not a standalone gate",
        "no CLI",
        "no committed output artifact or baseline",
        "no independent CI job or required-check name",
        "pytest assertions are the executable authority",
        "Python 3.11",
        "CONTRIBUTING.md",
        "Backend Tests",
        "control lane",
        "forced lane",
        "lc_source=summarization",
        "application-owned persisted projections",
        "context.projection_invalid",
        "context.*_changed",
        "named pytest assertion failure",
        "Application projection evaluator",
        "Projection input validation",
        "Framework or application traversal assertion",
        "project_context_reliability_outcome",
        "compare_context_reliability_outcomes",
        "scripts/agent_evaluation_context.py::project_context_reliability_outcome",
        "scripts/agent_evaluation_context.py::compare_context_reliability_outcomes",
        "agent/deepagents_harness.py::build_generic_harness",
        "api/research_execution_service.py::ResearchExecutionService.execute",
        "api/server.py::_run_dispatched_with_persistence",
        "api/run_repository.py::finalize_run_transaction",
        "api/run_repository.py::get_run",
        "api/run_result_service.py::resolve_run_result",
        "tools/tavily_tools.py::search_with_dedup",
        "tools/tavily_tools.py::clear_search_cache",
        "tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary",
        "tests/integration/test_context_reliability_regression.py::test_control_and_forced_lanes_observe_native_summary_only_when_forced",
        "tests/integration/test_context_reliability_regression.py::test_paired_persisted_application_outcomes_remain_equivalent",
        "tests/integration/test_context_reliability_regression.py::test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache",
        "Do not delete a projected dimension or loosen equality.",
        "Do not create or update a baseline.",
        "Do not patch or replace native middleware.",
        "Do not change production behavior to make the pack pass.",
    ):
        assert phrase in collapsed
    for operation in ("`build`", "`check`", "`accept`", "`regenerate`"):
        assert f"no {operation} operation" in collapsed
    for command in (
        "python -m pytest -q tests/unit/test_agent_evaluation_context.py",
        "tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary",
        "tests/integration/test_context_reliability_regression.py",
        'python -m pytest -q -m "not docker"',
        "python scripts/final_presentation_audit.py --root .",
        "git diff --check",
    ):
        assert command in reference
    assert "Context Reliability Pytest Regression Pack" in docs_index
    assert "(reference/context-reliability-regression.md)" in docs_index
    assert "fixed test count" not in reference
    assert "seconds to pass" not in reference
```

- [ ] **Step 2: Run the documentation node and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_documentation_contracts.py::test_context_reliability_pytest_pack_is_documented_and_indexed
```

Expected: FAIL with `FileNotFoundError` for `docs/reference/context-reliability-regression.md`.

- [ ] **Step 3: Write the reference page with fixed sections**

Create `docs/reference/context-reliability-regression.md` with:

```markdown
# Context Reliability Pytest Regression Pack

This is a pytest-collected regression pack, not a standalone gate. It has no
CLI, no `build` operation, no `check` operation, no `accept` operation, and no
`regenerate` operation. It creates no committed output artifact or baseline and
has no independent CI job or required-check name. Pytest assertions are the
executable authority, and the existing `Backend Tests` generic pytest command
collects the pack.

## Setup

Use the Python 3.11 contributor environment documented in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). The pack is provider-free,
credential-free, network-free, and Docker-free.

## Commands

Fast projection/evaluator check:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_agent_evaluation_context.py
```

Complete focused pack:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

Diagnostic rerun:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -vv -x tests/integration/test_context_reliability_regression.py
```

CI parity and public-document verification:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
python scripts/final_presentation_audit.py --root .
git diff --check
```

## Passing Semantics

Passing means exit code zero with every selected test passing. The control lane
records no native summary call. The forced lane records
`lc_source=summarization`, a subsequent coordinator model call receiving the
summary message, and canonical `write_file`. The paired comparison returns an
empty ordered finding list for the enumerated application-owned persisted
projections.

## Failure Diagnosis

| Symptom | Owner | First exact symbol or file to inspect | Prohibited false fix |
|---|---|---|---|
| An ordered `context.*_changed` finding | Application projection evaluator | `scripts/agent_evaluation_context.py::compare_context_reliability_outcomes` | Do not delete a projected dimension or loosen equality. |
| `context.projection_invalid` | Projection input validation | `scripts/agent_evaluation_context.py::project_context_reliability_outcome` | Do not accept malformed input, expose raw values, or create or update a baseline. |
| A named pytest assertion failure for activation, traversal, Evidence, deduplication, or cleanup | Framework or application traversal assertion | The failing stable node in `tests/unit/test_deepagents_harness.py` or `tests/integration/test_context_reliability_regression.py` | Do not patch or replace native middleware. Do not change production behavior to make the pack pass. |

Malformed projections expose no raw field value. The three diagnosis classes
remain distinct: application projection drift belongs to the evaluator,
projection rejection belongs to input validation, and named assertion failures
belong to the exact framework or application traversal boundary named by pytest.

## Code Navigation

- `scripts/agent_evaluation_context.py::project_context_reliability_outcome`
  validates and hashes persisted state.
- `scripts/agent_evaluation_context.py::compare_context_reliability_outcomes`
  emits stable ordered findings.
- `agent/deepagents_harness.py::build_generic_harness` installs the native
  coordinator middleware.
- `api/research_execution_service.py::ResearchExecutionService.execute` owns
  runtime context, Evidence freeze, and run-cache cleanup.
- `api/server.py::_run_dispatched_with_persistence` crosses the start fence.
- `api/run_repository.py::finalize_run_transaction` performs fenced atomic
  finalization.
- `api/run_repository.py::get_run` reads the application-owned persisted run.
- `api/run_result_service.py::resolve_run_result` resolves the selected result.
- `tools/tavily_tools.py::search_with_dedup` owns exact sequential search
  deduplication.
- `tools/tavily_tools.py::clear_search_cache` clears the run-scoped cache.
- `tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary`
  characterizes the locked middleware/profile boundary.
- `tests/integration/test_context_reliability_regression.py::test_control_and_forced_lanes_observe_native_summary_only_when_forced`
  locks paired summary activation.
- `tests/integration/test_context_reliability_regression.py::test_paired_persisted_application_outcomes_remain_equivalent`
  locks persisted application equivalence.
- `tests/integration/test_context_reliability_regression.py::test_forced_lane_preserves_nested_evidence_and_clears_exact_search_cache`
  locks nested Evidence, post-summary exact sequential deduplication, and
  cleanup.

## Safe Updates And Stop Rules

- If the locked DeepAgents version changes, adjust only the test profile or
  bounded payload required to preserve one non-triggered and one forced lane.
- If application authority gains a new projected field, add the projection
  field, negative control, and finding code together.
- Investigate any paired application drift as a RED result.
- Do not delete a projected dimension or loosen equality.
- Do not create or update a baseline.
- Do not patch or replace native middleware.
- Do not change production behavior to make the pack pass.
- Stop and request architecture review if the forced lane changes an
  application-owned projection.
- Stop and request architecture review if native summarization cannot be
  triggered through the locked framework without patching or replacing it.
- Stop and request architecture review if production middleware, API,
  database, dependency, CI, release, or consumer changes appear necessary.
- Stop and request architecture review if exact sequential deduplication fails
  outside its existing bounded contract.
- Stop and request architecture review if passing would require hiding drift,
  deleting a dimension, accepting a baseline, or exposing private content.
- Stop and request architecture review if the pack cannot remain
  deterministic, provider-free, network-free, Docker-free, and bounded in
  existing CI.

## Scope And Non-Claims

For one fixed synthetic generic scenario under `deepagents==0.6.11`, the
provider-free paired pytest regression observes native coordinator
summarization only in the forced lane and checks that the enumerated
application-owned persisted projections remain equivalent to the control lane.

This pack does not prove:

- live-provider summary quality;
- arbitrary-task or unlimited-context reliability;
- preservation of every URL, task-list entry, stop condition, or semantic
  detail;
- generic required-domain enforcement;
- concurrent or semantic duplicate-search prevention;
- production scale, latency, business impact, or user adoption;
- any change to DRA v0.1.6 or an existing consumer contract.
```

- [ ] **Step 4: Add one docs-index entry**

Insert after Agent Evaluation Regression Gate:

```markdown
- [Context Reliability Pytest Regression Pack](reference/context-reliability-regression.md)
  — provider-free paired native-summary regression over application-owned
  persisted projections.
```

- [ ] **Step 5: Run the documentation node and correct exact wording**

Run the Step 2 command.

Expected: PASS.

- [ ] **Step 6: Run the full documentation contract module**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_documentation_contracts.py
```

Expected: PASS with all existing and new documentation contracts passing.

- [ ] **Step 7: Commit the documentation slice**

```bash
git add \
  tests/unit/test_documentation_contracts.py \
  docs/reference/context-reliability-regression.md \
  docs/README.md
git commit -m "docs(context): document pytest regression pack"
```

---

### Task 7: Run Focused, CI-Parity, Presentation, And Diff Verification

**Files:**

- Verify only: all seven implementation files

- [ ] **Step 1: Confirm the implementation diff stays within seven files**

Run:

```bash
DRA_CONTEXT_IMPL_BASE=$(
  git log -1 --format=%H -- \
    docs/superpowers/plans/2026-07-25-context-reliability-regression-implementation-plan.md
)
test -n "${DRA_CONTEXT_IMPL_BASE}"
git diff --name-status "${DRA_CONTEXT_IMPL_BASE}...HEAD"
```

The command derives the implementation base from the commit that contains this plan. It deliberately does not embed that commit’s self-referential SHA. Expected exact paths:

```text
A scripts/agent_evaluation_context.py
A tests/unit/test_agent_evaluation_context.py
M tests/unit/test_deepagents_harness.py
A tests/integration/test_context_reliability_regression.py
M tests/unit/test_documentation_contracts.py
A docs/reference/context-reliability-regression.md
M docs/README.md
```

Stop if any production, API, DB, tool, dependency, CI, baseline, top-level README, CHANGELOG, release, or consumer file appears.

- [ ] **Step 2: Run the fast projection check**

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q tests/unit/test_agent_evaluation_context.py
```

Expected: exit 0 with every selected test passing.

- [ ] **Step 3: Run the complete focused pack**

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py::test_locked_native_summarizer_profile_forces_coordinator_summary \
  tests/integration/test_context_reliability_regression.py
```

Expected: exit 0 with every selected test passing.

- [ ] **Step 4: Run the diagnostic command once as a contract check**

```bash
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -vv -x tests/integration/test_context_reliability_regression.py
```

Expected: exit 0; node names clearly separate activation, paired persistence, and Evidence/cache behavior.

- [ ] **Step 5: Run CI-parity non-Docker pytest**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
```

Expected: exit 0. Do not promise or document a fixed count or elapsed time.

- [ ] **Step 6: Run public presentation and whitespace audits**

```bash
python scripts/final_presentation_audit.py --root .
git diff --check
```

Expected: presentation audit returns `{"status": "ok", "violations": []}` and `git diff --check` exits 0.

- [ ] **Step 7: Scan for private content and placeholders**

Run:

```bash
rg -n -i \
  'task[_-]label|review[_-]owner|return[_-]target|/U[sers]/|C[areer]|credential[[:space:]]+value|api[_-]?key=|s[ecret]=|T[B]D|T[O]DO|implement[[:space:]]+later|similar[[:space:]]+to' \
  scripts/agent_evaluation_context.py \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_context_reliability_regression.py \
  tests/unit/test_documentation_contracts.py \
  docs/reference/context-reliability-regression.md \
  docs/README.md
```

Expected: no private data or plan placeholder match. Review any legitimate public word match manually; do not suppress the scan globally.

- [ ] **Step 8: Review application equivalence and stop conditions**

Read the final forced-lane assertions and confirm all are true:

```text
native nested Evidence precedes the large task result
native summary call precedes the post-summary coordinator call
post-summary coordinator call precedes two exact sequential post-summary tool emissions
two post-summary tool emissions produce one underlying provider call
the second bounded task result precedes canonical write_file
control summary call count is zero
forced summary call count is one
both lanes use identical query, task args, search payloads, large task result,
and report bytes
both lanes reach state_version 2 and started dispatch
both initial segments are completed
both failure causes are null
both expose exactly one research-report.md artifact
both resolve successfully
paired comparison returns []
underlying post-summary duplicate search count is one
both run-scoped cache entries are absent after return
```

If any item is false, keep the branch RED and return to architecture review.

- [ ] **Step 9: Review type and signature consistency**

Confirm these exact pairs match across implementation and tests:

```text
project_context_reliability_outcome(*, run, resolution)
compare_context_reliability_outcomes(control, forced)
ResolvedRunResult.artifact["content_hash"]
RunResultUnavailable.status_code / code
ResearchExecutionService.execute(query, thread_id, *, run_id, segment_id,
                                 outcome_box, profile_id, scope)
_run_dispatched_with_persistence(claim, *, db_path, outcome_box, stage,
                                 termination_origin, finalization_checkpoint)
```

Correct mismatched names or annotations and rerun Steps 2–6.

- [ ] **Step 10: Create the final verification commit only if needed**

If verification required code or documentation corrections:

```bash
git add \
  scripts/agent_evaluation_context.py \
  tests/unit/test_agent_evaluation_context.py \
  tests/unit/test_deepagents_harness.py \
  tests/integration/test_context_reliability_regression.py \
  tests/unit/test_documentation_contracts.py \
  docs/reference/context-reliability-regression.md \
  docs/README.md
git commit -m "test(context): close regression verification"
```

If no file changed, do not create an empty commit.

- [ ] **Step 11: Confirm final clean state**

Run:

```bash
git status --short --branch
DRA_CONTEXT_IMPL_BASE=$(
  git log -1 --format=%H -- \
    docs/superpowers/plans/2026-07-25-context-reliability-regression-implementation-plan.md
)
test -n "${DRA_CONTEXT_IMPL_BASE}"
git log --oneline --decorate "${DRA_CONTEXT_IMPL_BASE}..HEAD"
```

Expected: the branch is clean and contains only the serial semantic commits from Tasks 1–7.

## Implementation Handoff

Plan complete. After explicit authority approval, this same current execution window, branch, and worktree continues with `superpowers:executing-plans` and executes Tasks 1–7 serially. It must not use subagents, parallel lanes, another worktree, or another branch. This plan landing does not authorize implementation; implementation remains paused until that follow-up approval. It also does not authorize provider/network/Docker execution, push, PR, merge, tag, release, deployment, publication, or cleanup.
