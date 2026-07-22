"""DeepAgents-native generic research harness assembly."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping

from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain.agents.middleware.tool_call_limit import (
    ToolCallLimitExceededError,
)
from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langgraph.errors import GraphRecursionError

from agent.harness_contracts import CallBudgetDiagnostic, HarnessExecutionError
from agent.profile_middleware import build_profile_middleware
from agent.profile_registry import profile_registry
from agent.research_agents import compile_generic_researchers
from agent.runtime_context import ResearchRuntimeContext
from agent.talent_runtime import talent_recursion_limit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SKILLS_ROOT = _REPOSITORY_ROOT / "skills"
_REQUIRED_SKILLS = (
    "research-planning",
    "evidence-synthesis-and-reporting",
)

GENERIC_COORDINATOR_PROMPT = """
Coordinate bounded research using only the named researchers and server-owned
tools. Read the available Skills before planning. Keep working notes under
/workspace/. Record evidence gaps instead of inventing facts. When synthesis
is complete, write the canonical Markdown candidate exactly to
/workspace/research-report.md.
""".strip()


class HarnessConfigurationError(RuntimeError):
    """Stable fail-closed error for invalid harness release assets."""


@dataclass(frozen=True)
class DeepAgentsHarness:
    """Compiled generic graph plus its server-owned harness policy."""

    graph: Any
    backend: CompositeBackend
    permissions: tuple[FilesystemPermission, ...]
    skills: tuple[str, ...]
    profile_graphs: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_graphs",
            MappingProxyType(dict(self.profile_graphs)),
        )

    def backend_contract(self) -> dict[str, Any]:
        skills_backend = self.backend.routes["/skills/"]
        return {
            "default": type(self.backend.default).__name__,
            "routes": {
                route: type(backend).__name__
                for route, backend in self.backend.routes.items()
            },
            "virtual_mode": skills_backend.virtual_mode,
        }

    def permission_for(
        self,
        operation: Literal["read", "write"],
        path: str,
    ) -> str:
        for rule in self.permissions:
            if operation not in rule.operations:
                continue
            if any(_matches_permission_path(path, pattern) for pattern in rule.paths):
                return rule.mode
        return "allow"

    def with_profile_graph(self, profile_id: str, graph: Any) -> DeepAgentsHarness:
        return DeepAgentsHarness(
            graph=self.graph,
            backend=self.backend,
            permissions=self.permissions,
            skills=self.skills,
            profile_graphs={**self.profile_graphs, profile_id: graph},
        )

    async def execute(self, request, *, runtime_context, observer):
        try:
            graph = self.profile_graphs[request.profile_id]
        except KeyError as exc:
            raise KeyError(f"unknown profile: {request.profile_id}") from exc
        content = request.query
        if request.profile_id == "talent-hiring-signal":
            content = (
                f"{request.query}\n\n"
                "【受限研究范围】\n"
                f"{json.dumps(dict(request.scope), ensure_ascii=False, sort_keys=True)}\n"
                "只研究上述声明范围，并返回 schema-valid ResearchPacket。"
            )
        config = {
            "configurable": {"thread_id": request.thread_id},
            "callbacks": list(observer.callbacks()),
            "metadata": dict(request.trace_metadata),
        }
        if request.profile_id == "talent-hiring-signal":
            config["recursion_limit"] = talent_recursion_limit()
        try:
            async for chunk in graph.astream(
                {"messages": [{"role": "user", "content": content}]},
                config=config,
                context=runtime_context,
            ):
                observer.on_stream_chunk(chunk)
        except (
            ModelCallLimitExceededError,
            ToolCallLimitExceededError,
        ) as exc:
            raise HarnessExecutionError(
                failure_kind="call_budget_exceeded",
                message=str(exc),
                call_budget_diagnostic=_call_budget_diagnostic(exc),
            ) from exc
        except GraphRecursionError as exc:
            raise HarnessExecutionError(
                failure_kind="recursion_limit_exceeded",
                message=str(exc),
            ) from exc
        return observer.snapshot_outcome()


def _call_budget_diagnostic(
    exc: ModelCallLimitExceededError | ToolCallLimitExceededError,
) -> CallBudgetDiagnostic | None:
    try:
        if isinstance(exc, ModelCallLimitExceededError):
            limiter_kind = "model"
            tool_scope = "not_applicable"
        elif isinstance(exc, ToolCallLimitExceededError):
            limiter_kind = "tool"
            if exc.tool_name is None:
                tool_scope = "all_tools"
            elif exc.tool_name == "task":
                tool_scope = "task"
            else:
                return None
        return CallBudgetDiagnostic(
            limiter_kind=limiter_kind,
            tool_scope=tool_scope,
            run_count=exc.run_count,
            run_limit=exc.run_limit,
            thread_count=exc.thread_count,
            thread_limit=exc.thread_limit,
            agent_role="not_observed",
        )
    except (AttributeError, TypeError, ValueError):
        return None


def _matches_permission_path(path: str, pattern: str) -> bool:
    if pattern == "/**":
        return path.startswith("/")
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(f"{prefix}/")
    return path == pattern


def build_filesystem_permissions() -> list[FilesystemPermission]:
    """Build the security-critical first-match-wins permission list."""
    return [
        FilesystemPermission(
            operations=["write"],
            paths=["/skills/**"],
            mode="deny",
        ),
        FilesystemPermission(
            operations=["read"],
            paths=["/skills/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/workspace/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**"],
            mode="deny",
        ),
    ]


def _read_required_skills(skills_root: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    try:
        for name in _REQUIRED_SKILLS:
            path = skills_root / name / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            if (
                not content.startswith("---\n")
                or f"\nname: {name}\n" not in content
                or "\ndescription:" not in content
            ):
                raise ValueError(f"incomplete Skill: {name}")
            loaded[name] = content
    except (OSError, UnicodeError, ValueError) as exc:
        raise HarnessConfigurationError("harness_assets_missing") from exc
    return loaded


def load_skill_names(
    profile_id: str,
    *,
    skills_root: Path | None = None,
) -> set[str]:
    if profile_id == "talent-hiring-signal":
        return set()
    if profile_id != "generic":
        raise KeyError(f"unknown profile: {profile_id}")
    return set(_read_required_skills(skills_root or _DEFAULT_SKILLS_ROOT))


def _register_generic_harness_profile(model: Any) -> None:
    if isinstance(model, str):
        provider = model.split(":", 1)[0]
    else:
        get_ls_params = getattr(model, "_get_ls_params", None)
        params = get_ls_params() if callable(get_ls_params) else {}
        provider = params.get("ls_provider")
    if not isinstance(provider, str) or not provider:
        raise HarnessConfigurationError("harness_model_profile_unavailable")
    register_harness_profile(
        provider,
        HarnessProfile(
            excluded_tools=frozenset({"execute"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(
                enabled=False,
            ),
        ),
    )


def build_generic_harness(
    *,
    model: Any,
    skills_root: Path | None = None,
) -> DeepAgentsHarness:
    """Compile the generic coordinator from release-owned assets and policy."""
    root = (skills_root or _DEFAULT_SKILLS_ROOT).resolve()
    _read_required_skills(root)
    policy = profile_registry.policy_for("generic")
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(
                root_dir=root,
                virtual_mode=True,
            ),
        },
    )
    permissions = tuple(build_filesystem_permissions())
    researchers = compile_generic_researchers(model=model)
    _register_generic_harness_profile(model)
    graph = create_deep_agent(
        model=model,
        tools=[],
        system_prompt=GENERIC_COORDINATOR_PROMPT,
        middleware=build_profile_middleware("generic", role="coordinator"),
        subagents=list(researchers.values()),
        skills=list(policy.skills),
        permissions=list(permissions),
        backend=backend,
        context_schema=ResearchRuntimeContext,
        name="generic-research-coordinator",
    )
    return DeepAgentsHarness(
        graph=graph,
        backend=backend,
        permissions=permissions,
        skills=policy.skills,
        profile_graphs={"generic": graph},
    )
