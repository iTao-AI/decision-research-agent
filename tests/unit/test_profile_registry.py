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
    assert manifest["harness_policy"]["allowed_tools"] == ["internet_search"]
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
