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

from api.monitor import monitor
import asyncio
import uuid
import shutil
from pathlib import Path

from api.context import set_session_context, reset_session_context, set_thread_context
from api.thread_ids import safe_session_dir

from agent.run_result import AgentRunAccumulator, AgentRunResult, process_stream_chunk

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

project_root = Path(__file__).parents[1].resolve()
print(f"----------------project_root-----------------: {project_root}")


def _prepare_session_environment(thread_id: str):
    """Initialize session workspace (directory, file migration, path context)."""
    session_dir = safe_session_dir(project_root / "output", thread_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    session_dir_str = str(session_dir).replace("\\", "/")

    relative_session_dir = str(session_dir.relative_to(project_root)).replace("\\", "/")

    upload_dir = safe_session_dir(project_root / "updated", thread_id)
    uploaded_info = ""

    if upload_dir.exists():
        files = [f.name for f in upload_dir.iterdir() if f.is_file()]

        if files:
            for f in files:
                shutil.copy2(upload_dir / f, session_dir / f)

            uploaded_info = (f"\n    [已上传文件] 已加载到工作目录:\n" +
                             "\n".join([f"    - {f}" for f in files]) +
                             "\n    请优先使用工具读取并参考这些文件。")

    return session_dir_str, relative_session_dir, uploaded_info


def _process_stream_chunk(chunk, accumulator: AgentRunAccumulator):
    """Process LangGraph stream output and report events to frontend."""
    process_stream_chunk(chunk, accumulator, monitor)


async def run_deep_agent(task_query: str, thread_id: str = None) -> AgentRunResult:
    """Main agent execution entry point."""
    if not thread_id:
        thread_id = str(uuid.uuid4())
    print(f"--- Start Task: {task_query} (Thread: {thread_id}) ---")

    session_dir_str, relative_session_dir, uploaded_info = _prepare_session_environment(thread_id)

    thread_token = set_thread_context(thread_id)
    session_token = set_session_context(session_dir_str)
    monitor.report_session_dir(session_dir_str)
    accumulator = AgentRunAccumulator(
        thread_id=thread_id,
        query=task_query,
        session_dir=Path(session_dir_str),
    )

    # Register token tracking callback
    from agent.token_tracking import TokenTrackingCallbackHandler
    token_callback = TokenTrackingCallbackHandler(thread_id=thread_id)

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [token_callback],
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

    try:
        async for chunk in main_agent.astream(
                {"messages": [{"role": "user", "content": task_query + path_instruction}]},
                config=config
        ):
            _process_stream_chunk(chunk, accumulator)
        return accumulator.to_result()
    except Exception as e:
        print(f"Error: {e}")
        monitor._emit("error", f"Execution failed: {e}")
        raise
    finally:
        if 'session_token' in locals():
            reset_session_context(session_token, thread_token)
        shared_context.clear_facts(thread_id)
        clear_search_cache(thread_id)


# ====================== 本地测试入口 ======================
if __name__ == "__main__":
    task = "查询数据库中的信息，生成一个pdf文件！"
    asyncio.run(run_deep_agent(task))
