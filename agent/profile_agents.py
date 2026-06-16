"""Compile immutable Deep Agents graphs from server-side profile policy."""
from __future__ import annotations

from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from agent.profile_registry import AgentHarnessPolicy, ProfileSpec
from agent.talent_contracts import ResearchPacket
from tools.talent_search import talent_public_search
from tools.provided_aggregate import provided_aggregate


TALENT_COORDINATOR_PROMPT = """
You are the Talent Hiring Signal research coordinator.
Delegate the bounded research scope to the general-purpose researcher exactly once.
Do not use undeclared sources or infer market-wide statistics from declared samples.
If the scope declares provided_aggregate, the researcher must call provided_aggregate
and use the returned evidence_id values in every finding and claim.
Do not call filesystem, todo, markdown, PDF, or file listing tools. Do not write files.
After the researcher returns, stop. Do not reformat the packet into Markdown.
Return only conclusions grounded in the researcher's structured packet.
""".strip()

TALENT_RESEARCHER_PROMPT = """
You are the bounded Hiring Signal Researcher.
Use only internet_search or provided_aggregate and only for the declared sample scope.
If provided_aggregate is declared, call provided_aggregate with the declared aggregate_id
before producing the packet. Use the exact evidence_id values returned by tools in
every finding.evidence_refs and claim.evidence_refs; never invent placeholder IDs
such as E-001.
Your final response must be a ResearchPacket structured-output tool call, not Markdown
and not a JSON wrapper. The top-level fields are exactly packet_id, scope_id, findings,
candidate_claims, contradictions, and limitations.
Each finding object must use statement and evidence_refs. Each claim object must use
text, finding_refs, evidence_refs, citation_status, verification_status, review_status,
and conflict_status.
Every claim must reference findings and evidence.
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
    researcher_agent = create_agent(
        model=model,
        tools=[talent_public_search, provided_aggregate],
        system_prompt=TALENT_RESEARCHER_PROMPT,
        response_format=ToolStrategy(ResearchPacket),
        name="general-purpose",
    )
    researcher = {
        "name": "general-purpose",
        "description": "Research the declared Talent Hiring Signal scope.",
        "runnable": researcher_agent,
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
