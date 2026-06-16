import pytest


def test_unknown_profile_fails_closed():
    from agent.profile_registry import profile_registry

    with pytest.raises(KeyError, match="unknown profile"):
        profile_registry.get("unknown")


def test_talent_profile_manifest_has_restricted_general_purpose_override():
    from agent.profile_registry import profile_registry

    manifest = profile_registry.manifest("talent-hiring-signal")

    assert manifest["harness_policy"]["backend"] == "state"
    assert manifest["harness_policy"]["skills"] == []
    assert manifest["harness_policy"]["subagents"] == ["general-purpose"]
    assert manifest["harness_policy"]["allowed_tools"] == [
        "internet_search",
        "provided_aggregate",
    ]
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

    captured = {}
    captured_researcher = {}

    def capture_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return object()

    def capture_create_agent(**kwargs):
        captured_researcher.update(kwargs)
        return {"compiled": "researcher"}

    monkeypatch.setattr(profile_agents, "create_deep_agent", capture_create_deep_agent)
    monkeypatch.setattr(profile_agents, "create_agent", capture_create_agent)
    profile = profile_registry.get("talent-hiring-signal")
    policy = profile_registry.policy_for("talent-hiring-signal")

    profile_agents.compile_profile_agent(
        profile,
        policy,
        model=object(),
        generic_agent=object(),
    )

    assert captured["tools"] == []
    assert captured["skills"] == []
    assert captured["response_format"] is None
    assert captured["backend"].__class__.__name__ == "StateBackend"
    assert [(rule.operations, rule.paths, rule.mode) for rule in captured["permissions"]] == [
        (["write"], ["/**"], "deny"),
        (["read"], ["/**"], "deny"),
    ]
    assert len(captured["subagents"]) == 1
    researcher = captured["subagents"][0]
    assert researcher["name"] == "general-purpose"
    assert researcher["runnable"] == {"compiled": "researcher"}
    assert captured_researcher["name"] == "general-purpose"
    assert isinstance(captured_researcher["response_format"], ToolStrategy)
    assert captured_researcher["response_format"].schema is ResearchPacket
    assert [tool.name for tool in captured_researcher["tools"]] == [
        "internet_search",
        "provided_aggregate",
    ]
