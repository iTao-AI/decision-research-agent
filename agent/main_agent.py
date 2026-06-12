from agent.shared_context import SharedContext
from agent.sub_agents.knowledge_base_agent import knowledge_base_agent
from agent.sub_agents.database_query_agent import database_query_agent
from agent.sub_agents.network_search_agent import network_search_agent

from tools.markdown_tools import generate_markdown
from tools.pdf_tools import convert_md_to_pdf
from tools.upload_file_read_tool import read_file_content
from tools.tavily_tools import clear_search_cache

from deepagents import create_deep_agent

from agent.llm import model
from agent.prompts import main_agent_config
from agent.profile_agents import compile_profile_agent
from agent.profile_registry import AgentFactory, profile_registry

from api.monitor import monitor
import asyncio
import json
import uuid
import shutil
from pathlib import Path
from urllib.parse import urlparse

from api.context import (
    reset_execution_context,
    reset_session_context,
    set_run_context,
    set_segment_context,
    set_session_context,
    set_thread_context,
    set_allowed_source_domains_context,
)
from api.thread_ids import safe_session_dir

from agent.research import evidence_from_shared_context_snapshot, merge_evidence_entries
from agent.run_result import (
    AgentRunAccumulator,
    AgentRunResult,
    OutcomeBox,
    process_stream_chunk,
)

def _resolve_subagent(agent):
    """Agent 类实例或 dict 的适配转换"""
    if hasattr(agent, "to_dict"):
        return agent.to_dict()
    return agent

subagents_list = [
    _resolve_subagent(knowledge_base_agent),
    _resolve_subagent(database_query_agent),
    _resolve_subagent(network_search_agent)
]

# 跨 Agent 事实共享上下文（每模块级单例，按 thread_id 隔离）
shared_context = SharedContext()

main_agent = create_deep_agent(
    model=model,
    subagents=subagents_list,
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    system_prompt=main_agent_config["system_prompt"]
)
agent_factory = AgentFactory(
    profile_registry,
    lambda profile, policy: compile_profile_agent(
        profile,
        policy,
        model=model,
        generic_agent=main_agent,
    ),
)

project_root = Path(__file__).parents[1].resolve()
print(f"----------------project_root-----------------: {project_root}")


def _prepare_session_environment(thread_id: str, *, include_uploads: bool = True):
    """Initialize session workspace (directory, file migration, path context)."""
    session_dir = safe_session_dir(project_root / "output", thread_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    session_dir_str = str(session_dir).replace("\\", "/")

    relative_session_dir = str(session_dir.relative_to(project_root)).replace("\\", "/")

    upload_dir = safe_session_dir(project_root / "updated", thread_id)
    uploaded_info = ""

    if include_uploads and upload_dir.exists():
        files = [f.name for f in upload_dir.iterdir() if f.is_file()]

        if files:
            for f in files:
                shutil.copy2(upload_dir / f, session_dir / f)

            uploaded_info = (f"\n    [已上传文件] 已加载到工作目录:\n" +
                             "\n".join([f"    - {f}" for f in files]) +
                             "\n    请优先使用工具读取并参考这些文件。")

    return session_dir_str, relative_session_dir, uploaded_info


def _allowed_source_domains(scope: dict | None) -> tuple[str, ...]:
    domains = set()
    for sample in (scope or {}).get("declared_samples", []):
        if not isinstance(sample, dict):
            continue
        if sample.get("source_type") != "public_job_posting":
            continue
        hostname = urlparse(sample.get("reference", "")).hostname
        if hostname:
            domains.add(hostname.lower())
    return tuple(sorted(domains))


def _process_stream_chunk(chunk, accumulator: AgentRunAccumulator):
    """Process LangGraph stream output and report events to frontend."""
    process_stream_chunk(chunk, accumulator, monitor)


def _freeze_execution_outcome(
    accumulator: AgentRunAccumulator,
    outcome_box: OutcomeBox | None,
    *,
    error_message: str | None = None,
    failure_kind: str | None = None,
    cancellation_state: str | None = None,
) -> AgentRunResult:
    """Freeze all evidence and diagnostics before runtime-scoped cleanup."""
    execution_id = accumulator.run_id or accumulator.thread_id
    accumulator.diagnostics.extend(shared_context.get_diagnostics(execution_id))
    try:
        snapshot = shared_context.snapshot_facts(
            execution_id, topic="search_evidence"
        )
        snapshot_evidence = evidence_from_shared_context_snapshot(
            thread_id=accumulator.thread_id,
            query_text=accumulator.query,
            snapshot=snapshot,
        )
        evidence_entries = merge_evidence_entries(
            accumulator.evidence_entries, snapshot_evidence
        )
    except Exception as exc:
        accumulator.diagnostics.append(f"evidence_snapshot_failed:{type(exc).__name__}")
        evidence_entries = list(accumulator.evidence_entries)
        failure_kind = failure_kind or "evidence_snapshot_failed"

    outcome = accumulator.to_outcome(
        evidence_entries=evidence_entries,
        error_message=error_message,
        failure_kind=failure_kind,
        cancellation_state=cancellation_state,
    )
    if outcome_box is not None:
        outcome_box.publish(outcome)
    return outcome


async def run_deep_agent(
    task_query: str,
    thread_id: str = None,
    run_id: str | None = None,
    segment_id: str | None = None,
    outcome_box: OutcomeBox | None = None,
    profile_id: str = "generic",
    scope: dict | None = None,
) -> AgentRunResult:
    """Main agent execution entry point."""
    if not thread_id:
        thread_id = str(uuid.uuid4())
    execution_id = run_id or thread_id
    print(f"--- Start Task: {task_query} (Thread: {thread_id}) ---")

    session_dir_str, relative_session_dir, uploaded_info = _prepare_session_environment(
        execution_id,
        include_uploads=profile_id != "talent-hiring-signal",
    )

    thread_token = set_thread_context(thread_id)
    run_token = set_run_context(execution_id)
    segment_token = set_segment_context(segment_id)
    allowed_source_domains_token = set_allowed_source_domains_context(
        _allowed_source_domains(scope)
        if profile_id == "talent-hiring-signal"
        else ()
    )
    session_token = set_session_context(session_dir_str)
    monitor.report_session_dir(session_dir_str)
    accumulator = AgentRunAccumulator(
        thread_id=thread_id,
        query=task_query,
        session_dir=Path(session_dir_str),
        profile_id=profile_id,
        run_id=run_id,
        segment_id=segment_id,
    )

    # Register token tracking callback
    from agent.token_tracking import TokenTrackingCallbackHandler
    token_callback = TokenTrackingCallbackHandler(thread_id=execution_id)

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [token_callback],
        "metadata": {
            "research_run_id": execution_id,
            "thread_id": thread_id,
            "profile_id": profile_id,
        },
    }

    path_instruction = f"""
    【工作环境指令】
    工作目录: {relative_session_dir}
    {uploaded_info}

    规则：
    1. 新生成文件必须保存到工作目录：'{relative_session_dir}/filename'
    2. 使用相对路径，禁止使用绝对路径
    3. 若存在上传文件，请先分析内容
    """
    if profile_id == "talent-hiring-signal":
        path_instruction = (
            "\n【受限研究范围】\n"
            + json.dumps(scope or {}, ensure_ascii=False, sort_keys=True)
            + "\n只研究上述声明范围，并返回 schema-valid ResearchPacket。"
        )

    try:
        selected_agent = agent_factory.get(profile_id)
        async for chunk in selected_agent.astream(
                {"messages": [{"role": "user", "content": task_query + path_instruction}]},
                config=config
        ):
            _process_stream_chunk(chunk, accumulator)
        return _freeze_execution_outcome(accumulator, outcome_box)
    except asyncio.CancelledError as exc:
        _freeze_execution_outcome(
            accumulator,
            outcome_box,
            error_message=str(exc) or "Agent execution cancelled.",
            failure_kind="cancelled",
            cancellation_state="cancelled",
        )
        raise
    except Exception as e:
        _freeze_execution_outcome(
            accumulator,
            outcome_box,
            error_message=str(e),
            failure_kind="execution_error",
        )
        print(f"Error: {e}")
        monitor._emit("error", f"Execution failed: {e}")
        raise
    finally:
        if 'session_token' in locals():
            reset_session_context(session_token, thread_token)
        if 'run_token' in locals():
            reset_execution_context(
                run_token,
                segment_token=segment_token,
                allowed_source_domains_token=allowed_source_domains_token,
            )
        shared_context.clear_facts(execution_id)
        clear_search_cache(execution_id)


# ====================== 本地测试入口 ======================
if __name__ == "__main__":
    task = "查询数据库中的信息，生成一个pdf文件！"
    asyncio.run(run_deep_agent(task))
