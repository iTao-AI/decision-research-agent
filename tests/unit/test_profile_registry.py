import pytest


def test_unknown_profile_fails_closed():
    from agent.profile_registry import profile_registry

    with pytest.raises(KeyError, match="unknown profile"):
        profile_registry.get("unknown")


def test_generic_manifest_uses_deepagents_native_harness_policy():
    from agent.profile_registry import profile_registry

    manifest = profile_registry.manifest("generic")["harness_policy"]

    assert manifest["backend"] == "composite-state-skills-v1"
    assert manifest["allowed_tools"] == [
        "write_todos",
        "ls",
        "read_file",
        "glob",
        "grep",
        "write_file",
        "edit_file",
        "task",
    ]
    assert manifest["subagents"] == [
        "knowledge_base",
        "database_query",
        "network_search",
    ]
    assert manifest["skills"] == ["/skills/"]
    assert manifest["filesystem_permissions"] == [
        "deny:write:/skills/**",
        "allow:read:/skills/**",
        "allow:read,write:/workspace/**",
        "deny:read,write:/**",
    ]


def test_generic_manifest_removes_host_tools_and_general_purpose():
    from agent.profile_registry import profile_registry

    manifest = profile_registry.manifest("generic")["harness_policy"]

    assert "generate_markdown" not in manifest["allowed_tools"]
    assert "convert_md_to_pdf" not in manifest["allowed_tools"]
    assert "read_file_content" not in manifest["allowed_tools"]
    assert "general-purpose" not in manifest["subagents"]


def test_unknown_profile_fails_at_registry_boundary():
    from agent.profile_registry import profile_registry

    with pytest.raises(KeyError, match="unknown profile"):
        profile_registry.get("missing-profile")


def test_talent_profile_manifest_has_restricted_direct_researcher_policy():
    from agent.profile_registry import profile_registry

    manifest = profile_registry.manifest("talent-hiring-signal")

    assert manifest["harness_policy"]["backend"] == "state"
    assert manifest["harness_policy"]["skills"] == []
    assert manifest["harness_policy"]["subagents"] == []
    assert manifest["harness_policy"]["allowed_tools"] == []
    assert "generate_markdown" not in manifest["harness_policy"]["allowed_tools"]
    assert "convert_md_to_pdf" not in manifest["harness_policy"]["allowed_tools"]


def test_talent_profile_uses_renderer_v2_without_changing_other_versions():
    from agent.profile_registry import profile_registry

    profile = profile_registry.get("talent-hiring-signal")

    assert profile.renderer_version == "2"
    assert profile.version == "1"
    assert profile.brief_schema_version == "1"
    assert profile.canonicalization_version == "1"
    assert profile.harness_policy_id == "talent-restricted-v1"


def test_agent_factory_compiles_each_immutable_profile_policy_once():
    from agent.profile_registry import AgentFactory, profile_registry

    compiled = []

    def compiler(profile, policy):
        compiled.append((profile.profile_id, policy.policy_id))
        return {"profile": profile.profile_id, "policy": policy.policy_id}

    factory = AgentFactory(profile_registry, compiler)

    first = factory.get("talent-hiring-signal")
    second = factory.get("talent-hiring-signal")

    assert first is second
    assert compiled == [("talent-hiring-signal", "talent-restricted-v1")]


def test_talent_agent_compiler_enforces_restricted_harness(monkeypatch):
    import agent.profile_agents as profile_agents
    from langchain.agents.structured_output import ToolStrategy
    from agent.profile_registry import profile_registry
    from agent.runtime_context import ResearchRuntimeContext
    from agent.talent_contracts import ResearchPacket

    captured_researcher = {}

    class FakeResearcher:
        def with_config(self, config):
            return {"compiled": "researcher", "bound_config": config}

    def capture_create_agent(**kwargs):
        captured_researcher.update(kwargs)
        return FakeResearcher()

    monkeypatch.setattr(profile_agents, "create_agent", capture_create_agent)
    profile = profile_registry.get("talent-hiring-signal")
    policy = profile_registry.policy_for("talent-hiring-signal")

    profile_agents.compile_profile_agent(
        profile,
        policy,
        model=object(),
        generic_agent=object(),
    )

    assert captured_researcher["name"] == "talent-hiring-signal-researcher"
    assert isinstance(captured_researcher["response_format"], ToolStrategy)
    assert captured_researcher["response_format"].schema is ResearchPacket
    assert captured_researcher["context_schema"] is ResearchRuntimeContext
    assert captured_researcher["tools"] == []
    from agent.profile_middleware import middleware_contract

    assert middleware_contract(captured_researcher["middleware"]) == {
        "model_run_limit": 12,
        "global_tool_run_limit": None,
        "task_run_limit": None,
        "exit_behavior": "error",
        "named_tool_limits": {},
    }


def test_talent_compiler_leaves_recursion_budget_to_runtime_adapter(monkeypatch):
    import agent.profile_agents as profile_agents
    from agent.profile_registry import profile_registry

    class FakeResearcher:
        def __init__(self):
            self.bound_configs = []

        def with_config(self, config):
            self.bound_configs.append(config)
            return self

    def capture_create_agent(**kwargs):
        return FakeResearcher()

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")
    monkeypatch.setattr(profile_agents, "create_agent", capture_create_agent)
    profile = profile_registry.get("talent-hiring-signal")
    policy = profile_registry.policy_for("talent-hiring-signal")

    compiled = profile_agents.compile_profile_agent(
        profile,
        policy,
        model=object(),
        generic_agent=object(),
    )

    assert compiled.bound_configs == []


def test_canonical_talent_recursion_limit_is_used(monkeypatch):
    from agent.talent_runtime import talent_recursion_limit

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT", "41")

    assert talent_recursion_limit() == 41


@pytest.mark.parametrize("canonical_value", ["", "invalid", "0", "-1"])
def test_invalid_canonical_talent_recursion_limit_uses_default(
    monkeypatch,
    canonical_value,
):
    from agent.talent_runtime import (
        DEFAULT_TALENT_RECURSION_LIMIT,
        talent_recursion_limit,
    )

    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT",
        canonical_value,
    )

    assert talent_recursion_limit() == DEFAULT_TALENT_RECURSION_LIMIT


def test_missing_talent_recursion_limit_uses_default(monkeypatch):
    from agent.talent_runtime import (
        DEFAULT_TALENT_RECURSION_LIMIT,
        talent_recursion_limit,
    )

    monkeypatch.delenv(
        "DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT",
        raising=False,
    )

    assert talent_recursion_limit() == DEFAULT_TALENT_RECURSION_LIMIT


def test_talent_researcher_prompt_forbids_uncited_findings():
    from agent.profile_agents import TALENT_RESEARCHER_PROMPT

    assert "Never create a finding with empty evidence_refs" in TALENT_RESEARCHER_PROMPT
    assert "put it only in limitations" in TALENT_RESEARCHER_PROMPT
    assert "Do not invent evidence IDs" in TALENT_RESEARCHER_PROMPT
    assert "E-TC-001" in TALENT_RESEARCHER_PROMPT


def test_talent_researcher_prompt_uses_preloaded_evidence_not_runtime_tools():
    from agent.profile_agents import TALENT_RESEARCHER_PROMPT

    assert "Do not call provided_aggregate" in TALENT_RESEARCHER_PROMPT
    assert "Use declared sample_id or source URL values" in TALENT_RESEARCHER_PROMPT
