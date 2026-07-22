from pathlib import Path

import pytest
from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain.agents.middleware.tool_call_limit import (
    ToolCallLimitExceededError,
)
from langgraph.errors import GraphRecursionError


class FakeGraph:
    def with_config(self, _config):
        return self


def _capture_framework_assembly(monkeypatch):
    import deepagents.graph as deepagents_graph
    import agent.research_agents as research_agents

    captured = {}

    class FakeRunnable:
        def with_config(self, _config):
            return self

    def capture_researcher(**kwargs):
        return FakeRunnable()

    def capture_graph(*args, **kwargs):
        captured.update(kwargs)
        return FakeGraph()

    monkeypatch.setattr(research_agents, "create_agent", capture_researcher)
    monkeypatch.setattr(deepagents_graph, "create_agent", capture_graph)
    return captured


def test_generic_backend_routes_skills_read_only(monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from agent.deepagents_harness import build_generic_harness

    _capture_framework_assembly(monkeypatch)
    harness = build_generic_harness(model=FakeListChatModel(responses=["done"]))

    assert harness.backend_contract() == {
        "default": "StateBackend",
        "routes": {"/skills/": "FilesystemBackend"},
        "virtual_mode": True,
    }
    assert harness.permission_for("write", "/workspace/note.md") == "allow"
    assert (
        harness.permission_for(
            "write",
            "/skills/research-planning/SKILL.md",
        )
        == "deny"
    )
    assert harness.permission_for("read", "/etc/passwd") == "deny"


def test_filesystem_permissions_are_enforced_by_real_tools(tmp_path):
    from deepagents.backends import CompositeBackend, FilesystemBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langgraph.prebuilt.tool_node import ToolRuntime

    from agent.deepagents_harness import build_filesystem_permissions

    workspace_root = tmp_path / "state"
    workspace_root.mkdir()
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    backend = CompositeBackend(
        default=FilesystemBackend(
            root_dir=workspace_root,
            virtual_mode=True,
        ),
        routes={
            "/skills/": FilesystemBackend(
                root_dir=skills_root,
                virtual_mode=True,
            ),
        },
    )
    middleware = FilesystemMiddleware(
        backend=backend,
        _permissions=build_filesystem_permissions(),
    )
    runtime = ToolRuntime(
        state={},
        context=None,
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id="test-call",
        store=None,
    )
    tools = {tool.name: tool for tool in middleware.tools}

    denied = tools["write_file"].func(
        "/skills/research-planning/SKILL.md",
        "overwrite",
        runtime,
    )
    written = tools["write_file"].func(
        "/workspace/test.md",
        "ok",
        runtime,
    )
    read = tools["read_file"].func(
        "/workspace/test.md",
        runtime,
    )

    assert denied.status == "error"
    assert "permission denied" in str(denied.content)
    assert written.status == "success"
    assert "ok" in str(read.content)


def test_missing_skills_directory_fails_closed(tmp_path):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from agent.deepagents_harness import (
        HarnessConfigurationError,
        build_generic_harness,
    )

    with pytest.raises(
        HarnessConfigurationError,
        match="harness_assets_missing",
    ):
        build_generic_harness(
            model=FakeListChatModel(responses=["done"]),
            skills_root=tmp_path / "missing",
        )


def test_incomplete_skill_fails_closed(tmp_path):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from agent.deepagents_harness import (
        HarnessConfigurationError,
        build_generic_harness,
    )

    skill = tmp_path / "research-planning"
    skill.mkdir()
    (skill / "SKILL.md").write_text("incomplete", encoding="utf-8")

    with pytest.raises(
        HarnessConfigurationError,
        match="harness_assets_missing",
    ):
        build_generic_harness(
            model=FakeListChatModel(responses=["done"]),
            skills_root=tmp_path,
        )


def test_generic_skills_are_real_and_talent_has_none():
    from agent.deepagents_harness import load_skill_names

    assert load_skill_names("generic") == {
        "research-planning",
        "evidence-synthesis-and-reporting",
    }
    assert load_skill_names("talent-hiring-signal") == set()


def test_generic_skills_source_loads_required_skills_with_deepagents_loader(
    monkeypatch,
):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langgraph.runtime import Runtime

    from agent.deepagents_harness import build_generic_harness

    captured = _capture_framework_assembly(monkeypatch)
    harness = build_generic_harness(model=FakeListChatModel(responses=["done"]))

    skills_middleware = next(
        item
        for item in captured["middleware"]
        if type(item).__name__ == "SkillsMiddleware"
    )
    update = skills_middleware.before_agent({}, Runtime(), {})

    assert {skill["name"] for skill in update["skills_metadata"]} == {
        "research-planning",
        "evidence-synthesis-and-reporting",
    }
    assert {
        skill["path"]
        for skill in update["skills_metadata"]
    } == {
        "/skills/research-planning/SKILL.md",
        "/skills/evidence-synthesis-and-reporting/SKILL.md",
    }
    assert harness.skills == ("/skills/",)


def test_harness_profile_disables_general_purpose_and_execute(monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    import agent.deepagents_harness as deepagents_harness

    registered = {}

    def capture_register(provider, profile):
        registered["provider"] = provider
        registered["profile"] = profile

    _capture_framework_assembly(monkeypatch)
    monkeypatch.setattr(
        deepagents_harness,
        "register_harness_profile",
        capture_register,
    )

    deepagents_harness.build_generic_harness(
        model=FakeListChatModel(responses=["done"]),
    )

    profile = registered["profile"]
    assert profile.general_purpose_subagent.enabled is False
    assert profile.excluded_tools == frozenset({"execute"})


def test_pinned_deepagents_middleware_stack_and_subagents(monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from agent.deepagents_harness import build_generic_harness

    captured = _capture_framework_assembly(monkeypatch)
    build_generic_harness(model=FakeListChatModel(responses=["done"]))

    names = [
        getattr(type(item), "serialized_name", None) or type(item).__name__
        for item in captured["middleware"]
    ]
    assert any(name.endswith("ToolExclusionMiddleware") for name in names)
    assert [
        name for name in names if not name.endswith("ToolExclusionMiddleware")
    ] == [
        "TodoListMiddleware",
        "SkillsMiddleware",
        "FilesystemMiddleware",
        "SubAgentMiddleware",
        "SummarizationMiddleware",
        "PatchToolCallsMiddleware",
        "CanonicalReportCompletionMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "AnthropicPromptCachingMiddleware",
    ]
    subagent_middleware = captured["middleware"][3]
    assert subagent_middleware.subagent_names == {
        "network_search",
        "database_query",
        "knowledge_base",
    }
    assert "general-purpose" not in subagent_middleware.subagent_names


@pytest.mark.asyncio
async def test_runtime_config_is_owned_by_adapter(monkeypatch):
    from agent.deepagents_harness import DeepAgentsHarness
    from agent.harness_contracts import HarnessRequest
    from agent.runtime_context import ResearchRuntimeContext

    class CapturingGraph:
        def __init__(self):
            self.config = None

        async def astream(self, _input, *, config, context):
            self.config = config
            self.context = context
            if False:
                yield {}

    class Observer:
        def callbacks(self):
            return ["callback"]

        def on_stream_chunk(self, _chunk):
            raise AssertionError("no chunks expected")

        def snapshot_outcome(self):
            return "outcome"

    generic_graph = CapturingGraph()
    talent_graph = CapturingGraph()
    harness = DeepAgentsHarness(
        graph=generic_graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={
            "generic": generic_graph,
            "talent-hiring-signal": talent_graph,
        },
    )
    context = ResearchRuntimeContext(
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
    )

    await harness.execute(
        HarnessRequest(
            query="query",
            thread_id="thread-1",
            run_id="run-1",
            segment_id="segment-1",
            profile_id="generic",
            scope={},
            trace_metadata={"profile_id": "generic"},
        ),
        runtime_context=context,
        observer=Observer(),
    )
    assert generic_graph.config == {
        "configurable": {"thread_id": "thread-1"},
        "callbacks": ["callback"],
        "metadata": {"profile_id": "generic"},
    }

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")
    await harness.execute(
        HarnessRequest(
            query="query",
            thread_id="thread-1",
            run_id="run-1",
            segment_id="segment-1",
            profile_id="talent-hiring-signal",
            scope={},
            trace_metadata={"profile_id": "talent-hiring-signal"},
        ),
        runtime_context=context,
        observer=Observer(),
    )
    assert talent_graph.config["recursion_limit"] == 37


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("native_exception", "expected_failure_kind", "expected_diagnostic"),
    [
        pytest.param(
            ModelCallLimitExceededError(
                thread_count=40,
                run_count=40,
                thread_limit=None,
                run_limit=40,
            ),
            "call_budget_exceeded",
            {
                "limiter_kind": "model",
                "tool_scope": "not_applicable",
                "run_count": 40,
                "run_limit": 40,
                "thread_count": 40,
                "thread_limit": None,
                "agent_role": "not_observed",
            },
            id="model-call-limit",
        ),
        pytest.param(
            ToolCallLimitExceededError(
                thread_count=10,
                run_count=11,
                thread_limit=10,
                run_limit=10,
                tool_name=None,
            ),
            "call_budget_exceeded",
            {
                "limiter_kind": "tool",
                "tool_scope": "all_tools",
                "run_count": 11,
                "run_limit": 10,
                "thread_count": 10,
                "thread_limit": 10,
                "agent_role": "not_observed",
            },
            id="global-tool-call-limit",
        ),
        pytest.param(
            ToolCallLimitExceededError(
                thread_count=6,
                run_count=6,
                thread_limit=None,
                run_limit=5,
                tool_name="task",
            ),
            "call_budget_exceeded",
            {
                "limiter_kind": "tool",
                "tool_scope": "task",
                "run_count": 6,
                "run_limit": 5,
                "thread_count": 6,
                "thread_limit": None,
                "agent_role": "not_observed",
            },
            id="tool-call-limit",
        ),
        pytest.param(
            GraphRecursionError("bounded recursion"),
            "recursion_limit_exceeded",
            None,
            id="graph-recursion-limit",
        ),
    ],
)
async def test_installed_native_limit_signals_reach_bounded_harness_mapping(
    native_exception,
    expected_failure_kind,
    expected_diagnostic,
):
    from agent.deepagents_harness import DeepAgentsHarness
    from agent.harness_contracts import (
        CallBudgetDiagnostic,
        HarnessExecutionError,
        HarnessRequest,
    )
    from agent.runtime_context import ResearchRuntimeContext

    class RaisingGraph:
        async def astream(self, _input, *, config, context):
            del config, context
            if False:
                yield {}
            raise native_exception

    class Observer:
        def callbacks(self):
            return []

        def on_stream_chunk(self, _chunk):
            raise AssertionError("no chunks expected")

        def snapshot_outcome(self):
            raise AssertionError("native failure must not produce success")

    graph = RaisingGraph()
    harness = DeepAgentsHarness(
        graph=graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={"generic": graph},
    )
    request = HarnessRequest(
        query="query",
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
        scope={},
        trace_metadata={},
    )
    context = ResearchRuntimeContext(
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
    )

    with pytest.raises(HarnessExecutionError) as raised:
        await harness.execute(
            request,
            runtime_context=context,
            observer=Observer(),
        )

    assert raised.value.failure_kind == expected_failure_kind
    assert raised.value.__cause__ is native_exception
    assert raised.value.call_budget_diagnostic == (
        CallBudgetDiagnostic(**expected_diagnostic)
        if expected_diagnostic is not None
        else None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["coordinator", "subagent"])
@pytest.mark.parametrize(
    ("native_exception", "expected_kind"),
    [
        pytest.param(
            ModelCallLimitExceededError(
                thread_count=7,
                run_count=7,
                thread_limit=None,
                run_limit=7,
            ),
            "model",
            id="model",
        ),
        pytest.param(
            ToolCallLimitExceededError(
                thread_count=4,
                run_count=5,
                thread_limit=None,
                run_limit=4,
                tool_name="task",
            ),
            "tool",
            id="task-tool",
        ),
    ],
)
async def test_native_call_limit_projection_never_infers_agent_role(
    native_exception,
    expected_kind,
    origin,
):
    from agent.deepagents_harness import DeepAgentsHarness
    from agent.harness_contracts import HarnessExecutionError, HarnessRequest
    from agent.runtime_context import ResearchRuntimeContext

    class PropagatingGraph:
        async def astream(self, _input, *, config, context):
            del config, context
            assert origin in {"coordinator", "subagent"}
            if False:
                yield {}
            raise native_exception

    class Observer:
        def callbacks(self):
            return []

        def on_stream_chunk(self, _chunk):
            raise AssertionError("no chunks expected")

        def snapshot_outcome(self):
            raise AssertionError("native failure must not produce success")

    graph = PropagatingGraph()
    harness = DeepAgentsHarness(
        graph=graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={"generic": graph},
    )
    request = HarnessRequest(
        query="query",
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
        scope={},
        trace_metadata={},
    )
    context = ResearchRuntimeContext(
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
    )

    with pytest.raises(HarnessExecutionError) as raised:
        await harness.execute(
            request,
            runtime_context=context,
            observer=Observer(),
        )

    assert raised.value.failure_kind == "call_budget_exceeded"
    assert raised.value.call_budget_diagnostic.limiter_kind == expected_kind
    assert raised.value.call_budget_diagnostic.agent_role == "not_observed"
    assert raised.value.__cause__ is native_exception


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native_exception",
    [
        pytest.param(
            ToolCallLimitExceededError(1, 1, 1, 1, tool_name="search"),
            id="unknown-tool",
        ),
        pytest.param(
            ModelCallLimitExceededError(1, 1, 1, None),
            id="missing-run-limit",
        ),
        pytest.param(
            ModelCallLimitExceededError(1, True, 1, 1),
            id="boolean-count",
        ),
        pytest.param(
            ModelCallLimitExceededError(1, -1, 1, 1),
            id="negative-count",
        ),
        pytest.param(
            ModelCallLimitExceededError(1, 1, 1, 0),
            id="zero-limit",
        ),
        pytest.param(
            ModelCallLimitExceededError(1, 1_000_001, 1, 1),
            id="above-bound",
        ),
    ],
)
async def test_malformed_native_call_limit_keeps_public_kind_without_projection(
    native_exception,
):
    from agent.deepagents_harness import DeepAgentsHarness
    from agent.harness_contracts import HarnessExecutionError, HarnessRequest
    from agent.runtime_context import ResearchRuntimeContext

    class RaisingGraph:
        async def astream(self, _input, *, config, context):
            del config, context
            if False:
                yield {}
            raise native_exception

    class Observer:
        def callbacks(self):
            return []

        def on_stream_chunk(self, _chunk):
            raise AssertionError("no chunks expected")

        def snapshot_outcome(self):
            raise AssertionError("native failure must not produce success")

    graph = RaisingGraph()
    harness = DeepAgentsHarness(
        graph=graph,
        backend=object(),
        permissions=(),
        skills=(),
        profile_graphs={"generic": graph},
    )
    request = HarnessRequest(
        query="query",
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
        scope={},
        trace_metadata={},
    )
    context = ResearchRuntimeContext(
        thread_id="thread-1",
        run_id="run-1",
        segment_id="segment-1",
        profile_id="generic",
    )

    with pytest.raises(HarnessExecutionError) as raised:
        await harness.execute(
            request,
            runtime_context=context,
            observer=Observer(),
        )

    assert raised.value.failure_kind == "call_budget_exceeded"
    assert raised.value.call_budget_diagnostic is None
    assert raised.value.__cause__ is native_exception
