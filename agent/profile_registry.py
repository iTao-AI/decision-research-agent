"""Immutable server-side profile and Deep Agents harness policy registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from types import MappingProxyType
from typing import Any, Callable


@dataclass(frozen=True)
class AgentHarnessPolicy:
    policy_id: str
    backend: str
    allowed_tools: tuple[str, ...]
    subagents: tuple[str, ...]
    skills: tuple[str, ...] = ()
    filesystem_permissions: tuple[str, ...] = ("deny:write:/**",)


@dataclass(frozen=True)
class ProfileSpec:
    profile_id: str
    version: str
    harness_policy_id: str
    scope_schema: str
    finding_schema: str
    claim_policy: str
    review_policy: str
    brief_schema_version: str
    renderer_version: str
    canonicalization_version: str


GENERIC_POLICY = AgentHarnessPolicy(
    policy_id="generic-current-v1",
    backend="current",
    allowed_tools=("generate_markdown", "convert_md_to_pdf", "read_file_content"),
    subagents=("knowledge_base", "database_query", "network_search", "general-purpose"),
)
TALENT_POLICY = AgentHarnessPolicy(
    policy_id="talent-restricted-v1",
    backend="state",
    allowed_tools=(),
    subagents=(),
    skills=(),
    filesystem_permissions=("deny:write:/**", "deny:read:/**"),
)

GENERIC_PROFILE = ProfileSpec(
    profile_id="generic",
    version="1",
    harness_policy_id=GENERIC_POLICY.policy_id,
    scope_schema="freeform-query",
    finding_schema="EvidenceEntry",
    claim_policy="none",
    review_policy="none",
    brief_schema_version="legacy",
    renderer_version="legacy",
    canonicalization_version="legacy",
)
TALENT_PROFILE = ProfileSpec(
    profile_id="talent-hiring-signal",
    version="1",
    harness_policy_id=TALENT_POLICY.policy_id,
    scope_schema="ResearchScope",
    finding_schema="ResearchPacket",
    claim_policy="candidate-claims-v1",
    review_policy="deterministic-v1",
    brief_schema_version="1",
    renderer_version="2",
    canonicalization_version="1",
)


class ProfileRegistry:
    def __init__(
        self,
        profiles: tuple[ProfileSpec, ...],
        policies: tuple[AgentHarnessPolicy, ...],
    ):
        self._profiles = MappingProxyType({item.profile_id: item for item in profiles})
        self._policies = MappingProxyType({item.policy_id: item for item in policies})

    def get(self, profile_id: str) -> ProfileSpec:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown profile: {profile_id}") from exc

    def policy_for(self, profile_id: str) -> AgentHarnessPolicy:
        profile = self.get(profile_id)
        return self._policies[profile.harness_policy_id]

    def manifest(self, profile_id: str) -> dict[str, Any]:
        profile = self.get(profile_id)
        policy = self.policy_for(profile_id)
        return {
            "profile": asdict(profile),
            "harness_policy": {
                **asdict(policy),
                "allowed_tools": list(policy.allowed_tools),
                "subagents": list(policy.subagents),
                "skills": list(policy.skills),
                "filesystem_permissions": list(policy.filesystem_permissions),
            },
        }


class AgentFactory:
    """Compile immutable profile/policy pairs once and only select at runtime."""

    def __init__(
        self,
        registry: ProfileRegistry,
        compiler: Callable[[ProfileSpec, AgentHarnessPolicy], Any],
    ):
        self._registry = registry
        self._compiler = compiler
        self._compiled: dict[tuple[str, str, str], Any] = {}
        self._lock = Lock()

    def get(self, profile_id: str) -> Any:
        profile = self._registry.get(profile_id)
        policy = self._registry.policy_for(profile_id)
        key = (profile.profile_id, profile.version, policy.policy_id)
        with self._lock:
            if key not in self._compiled:
                self._compiled[key] = self._compiler(profile, policy)
            return self._compiled[key]


profile_registry = ProfileRegistry(
    profiles=(GENERIC_PROFILE, TALENT_PROFILE),
    policies=(GENERIC_POLICY, TALENT_POLICY),
)
