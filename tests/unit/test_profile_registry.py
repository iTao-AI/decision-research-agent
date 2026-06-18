import pytest


def test_unknown_profile_fails_closed():
    from agent.profile_registry import profile_registry

    with pytest.raises(KeyError, match="unknown profile"):
        profile_registry.get("unknown")


def test_talent_profile_manifest_has_restricted_direct_researcher_policy():
    from agent.profile_registry import profile_registry

    manifest = profile_registry.manifest("talent-hiring-signal")

    assert manifest["harness_policy"]["backend"] == "state"
    assert manifest["harness_policy"]["skills"] == []
    assert manifest["harness_policy"]["subagents"] == []
    assert manifest["harness_policy"]["allowed_tools"] == []
    assert "generate_markdown" not in manifest["harness_policy"]["allowed_tools"]
    assert "convert_md_to_pdf" not in manifest["harness_policy"]["allowed_tools"]


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
    assert captured_researcher["tools"] == []


def test_talent_compiled_researcher_binds_recursion_budget(monkeypatch):
    import agent.profile_agents as profile_agents
    from agent.profile_registry import profile_registry

    class FakeResearcher:
        def with_config(self, config):
            return {"compiled": "researcher", "bound_config": config}

    def capture_create_agent(**kwargs):
        return FakeResearcher()

    monkeypatch.setenv("DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")
    monkeypatch.setattr(profile_agents, "create_agent", capture_create_agent)
    profile = profile_registry.get("talent-hiring-signal")
    policy = profile_registry.policy_for("talent-hiring-signal")

    compiled = profile_agents.compile_profile_agent(
        profile,
        policy,
        model=object(),
        generic_agent=object(),
    )

    assert compiled["bound_config"]["recursion_limit"] == 37


def test_canonical_talent_recursion_limit_overrides_legacy(monkeypatch):
    from agent.talent_runtime import talent_recursion_limit

    monkeypatch.setenv("DECISION_RESEARCH_AGENT_TALENT_RECURSION_LIMIT", "41")
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")

    assert talent_recursion_limit() == 41


@pytest.mark.parametrize("canonical_value", ["", "invalid", "0", "-1"])
def test_invalid_canonical_talent_recursion_limit_uses_default_without_legacy(
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
    monkeypatch.setenv("DEEP_SEARCH_AGENT_TALENT_RECURSION_LIMIT", "37")

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
