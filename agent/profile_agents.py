"""Compile immutable Deep Agents graphs from server-side profile policy."""
from __future__ import annotations

from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import StateBackend

from agent.profile_registry import AgentHarnessPolicy, ProfileSpec
from agent.talent_contracts import ResearchPacket
from tools.talent_search import talent_public_search


TALENT_COORDINATOR_PROMPT = """
You are the Talent Hiring Signal research coordinator.
Delegate the bounded research scope to the general-purpose researcher.
Do not use undeclared sources or infer market-wide statistics from declared samples.
Return only conclusions grounded in the researcher's structured packet.
""".strip()

TALENT_RESEARCHER_PROMPT = """
You are the bounded Hiring Signal Researcher.
Use only internet_search and only for the declared public sample scope.
Return a schema-valid ResearchPacket. Every claim must reference findings and evidence.
State contradictions, evidence gaps, and limitations explicitly.
Never request or infer personal candidate data.
""".strip()


def _filesystem_permissions(policy: AgentHarnessPolicy) -> list[FilesystemPermission]:
    permissions = []
    for encoded in policy.filesystem_permissions:
        mode, operation, path = encoded.split(":", maxsplit=2)
        permissions.append(
            FilesystemPermission(
                operations=[operation],
                paths=[path],
                mode=mode,
            )
        )
    return permissions


def compile_profile_agent(
    profile: ProfileSpec,
    policy: AgentHarnessPolicy,
    *,
    model: Any,
    generic_agent: Any,
) -> Any:
    """Compile one immutable profile graph, failing closed for unknown policies."""
    if profile.profile_id == "generic":
        return generic_agent
    if profile.profile_id != "talent-hiring-signal":
        raise ValueError(f"unsupported profile compiler: {profile.profile_id}")
    if policy.policy_id != "talent-restricted-v1":
        raise ValueError(f"unsupported harness policy: {policy.policy_id}")

    permissions = _filesystem_permissions(policy)
    researcher = {
        "name": "general-purpose",
        "description": "Research the declared Talent Hiring Signal scope.",
        "system_prompt": TALENT_RESEARCHER_PROMPT,
        "tools": [talent_public_search],
        "skills": [],
        "permissions": permissions,
        "response_format": ResearchPacket,
    }
    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=TALENT_COORDINATOR_PROMPT,
        subagents=[researcher],
        skills=[],
        permissions=permissions,
        backend=StateBackend(),
        response_format=None,
        name="talent-hiring-signal-coordinator",
    )
