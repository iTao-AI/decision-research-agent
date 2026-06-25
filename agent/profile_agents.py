"""Compile immutable Deep Agents graphs from server-side profile policy."""
from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from agent.profile_registry import AgentHarnessPolicy, ProfileSpec
from agent.profile_middleware import build_profile_middleware
from agent.structured_output_recovery import pair_invalid_structured_tool_calls
from agent.talent_contracts import ResearchPacket
from agent.talent_runtime import talent_recursion_limit


TALENT_RESEARCHER_PROMPT = """
You are the bounded Hiring Signal Researcher.
Use only the declared source snapshot text in the prompt envelope.
Do not call provided_aggregate, internet_search, filesystem, todo, markdown, PDF,
or file listing tools.
Use declared sample_id or source URL values in every finding.evidence_refs and
claim.evidence_refs. Do not invent evidence IDs, placeholder IDs, or compact
labels such as E-001, E-TC-001, source-snapshot, or custom abbreviations.
Never create a finding with empty evidence_refs. If a limitation, caveat, or
evidence gap has no direct evidence_id, put it only in limitations instead of
findings or candidate_claims.
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

    return create_agent(
        model=model,
        tools=[],
        system_prompt=TALENT_RESEARCHER_PROMPT,
        response_format=ToolStrategy(ResearchPacket),
        middleware=[
            pair_invalid_structured_tool_calls,
            *build_profile_middleware(
                "talent-hiring-signal",
                role="researcher",
            ),
        ],
        name="talent-hiring-signal-researcher",
    ).with_config({"recursion_limit": talent_recursion_limit()})
