"""RAGFlow knowledge base tools with timeout and retry resilience.

All RAGFlow HTTP calls are wrapped with:
- 60-second timeout via asyncio.wait_for
- 3 retries with exponential backoff via retry_async
- Structured error strings for graceful degradation
"""
import asyncio
import logging
import os
from typing import Optional, Tuple

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from api.monitor import monitor
from tools.retry_utils import TIMEOUTS, retry_async

logger = logging.getLogger(__name__)


def _load_ragflow_env() -> Tuple[Optional[str], Optional[str]]:
    """Load RAGFlow environment variables."""
    return os.getenv("RAGFLOW_API_KEY"), os.getenv("RAGFLOW_API_URL")


# ---------------------------------------------------------------------------
# Async helpers — each wraps sync RAGFlow SDK calls with timeout + retry
# ---------------------------------------------------------------------------

async def _ragflow_list_chats(api_key: str, base_url: str):
    """List all RAGFlow chat assistants with timeout and retry."""
    timeout = TIMEOUTS["ragflow"]
    total_timeout = timeout * 3  # budget for all retries combined

    async def _do_list():
        loop = asyncio.get_running_loop()
        rag = RAGFlow(api_key=api_key, base_url=base_url)
        return await loop.run_in_executor(None, rag.list_chats)

    return await asyncio.wait_for(
        retry_async(_do_list, max_retries=3, service_name="ragflow-list"),
        timeout=total_timeout,
    )


async def _ragflow_find_chat(assistant_name: str, api_key: str, base_url: str):
    """Find a specific RAGFlow chat by name with timeout and retry."""
    timeout = TIMEOUTS["ragflow"]
    total_timeout = timeout * 3

    async def _do_find():
        loop = asyncio.get_running_loop()
        rag = RAGFlow(api_key=api_key, base_url=base_url)
        chats = await loop.run_in_executor(
            None, lambda: rag.list_chats(name=assistant_name)
        )
        return chats[0] if chats else None

    return await asyncio.wait_for(
        retry_async(_do_find, max_retries=3, service_name="ragflow-find-chat"),
        timeout=total_timeout,
    )


async def _ragflow_create_session(chat, session_name: str = "temp_session"):
    """Create a RAGFlow session with timeout and retry."""
    timeout = TIMEOUTS["ragflow"]
    total_timeout = timeout * 3

    async def _do_create():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: chat.create_session(name=session_name)
        )

    return await asyncio.wait_for(
        retry_async(_do_create, max_retries=3, service_name="ragflow-create-session"),
        timeout=total_timeout,
    )


async def _ragflow_ask(session, question: str) -> str:
    """Ask a RAGFlow session a question with timeout and retry.

    The entire stream consumption is wrapped so a hanging stream triggers retry.
    """
    timeout = TIMEOUTS["ragflow"]
    total_timeout = timeout * 3

    async def _do_ask():
        loop = asyncio.get_running_loop()

        def _consume_stream():
            response_stream = session.ask(question=question, stream=True)
            full_answer = ''
            for response in response_stream:
                if hasattr(response, "content") and response.content:
                    full_answer = response.content
            return full_answer

        return await loop.run_in_executor(None, _consume_stream)

    return await asyncio.wait_for(
        retry_async(_do_ask, max_retries=3, service_name="ragflow-ask"),
        timeout=total_timeout,
    )


async def _ragflow_delete_sessions(chat, session_ids: list):
    """Delete RAGFlow sessions (best-effort, no retry)."""
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: chat.delete_sessions(ids=session_ids)),
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Failed to delete RAGFlow session(s): {e}")


# ---------------------------------------------------------------------------
# Structured error formatting
# ---------------------------------------------------------------------------

def _format_degradation_error(operation: str, original_error: str) -> str:
    """Format a structured degradation error string."""
    return f"Error: knowledge base {operation} {'timed out after retries' if 'timeout' in original_error.lower() or 'timed out' in original_error.lower() else 'unavailable after retries'}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_assistant_list(dummy_arg: str = "") -> str:
    """Get info for all RAGFlow chat assistants."""
    monitor.report_tool("RAGFlow助手列表查询")
    api_key, base_url = _load_ragflow_env()

    if not api_key or not base_url:
        monitor.report_end("RAGFlow助手列表查询", error="RAGFlow 环境变量未配置")
        return "错误：RAGFlow 环境变量未配置（需设置 RAGFLOW_API_URL 与 RAGFLOW_API_KEY）"

    try:
        assistants = asyncio.run(_ragflow_list_chats(api_key, base_url))

        result = ""
        for assistant in assistants:
            kb_names = []
            if assistant.datasets and isinstance(assistant.datasets, list):
                for dataset in assistant.datasets:
                    if isinstance(dataset, dict) and "name" in dataset:
                        kb_names.append(dataset["name"])
            kb_names_str = "、".join(kb_names) if kb_names else "无"
            result += f"助手名称：{assistant.name}； 功能介绍：{assistant.description}； 关联知识库：{kb_names_str}\n"

        output = result.rstrip("\n") if result else "未找到任何聊天助手"
        monitor.report_end("RAGFlow助手列表查询", output)
        return output

    except (TimeoutError, asyncio.TimeoutError):
        monitor.report_end("RAGFlow助手列表查询", error="knowledge base query timed out after retries")
        return "Error: knowledge base query timed out after retries"
    except ConnectionError as e:
        monitor.report_end("RAGFlow助手列表查询", error="knowledge base service unavailable after retries")
        return f"Error: knowledge base service unavailable after retries"
    except Exception as e:
        monitor.report_end("RAGFlow助手列表查询", error=str(e))
        return f"获取助手列表失败：{str(e)}"


@tool
def create_ask_delete(assistant_name: str, question: str) -> str:
    """Ask a RAGFlow assistant a question (temporary session, deleted after use)."""
    monitor.report_tool(
        "RAGFlow助手提问工具",
        {"助手名称": assistant_name, "查询问题": question}
    )
    api_key, base_url = _load_ragflow_env()

    if not api_key or not base_url:
        monitor.report_end("RAGFlow助手提问工具", error="RAGFlow 环境变量未配置")
        return "错误：RAGFlow 环境变量未配置（需设置 RAGFLOW_API_URL 与 RAGFLOW_API_KEY）"

    session = None
    chat = None

    async def _execute():
        nonlocal session, chat

        # Step 1: Find the chat
        chat = await _ragflow_find_chat(assistant_name, api_key, base_url)
        if chat is None:
            return None, f"没有找到name:{assistant_name}的聊天助手！"

        # Step 2: Create a temporary session
        session = await _ragflow_create_session(chat)

        # Step 3: Ask the question
        full_answer = await _ragflow_ask(session, question)

        monitor.report_tool(
            "RAGFlow助手回答记录",
            {"助手名称": assistant_name, "问题": question, "答案": full_answer}
        )
        return full_answer, None

    try:
        answer, error = asyncio.run(_execute())

        if error:
            monitor.report_end("RAGFlow助手提问工具", error=error)
            return error

        monitor.report_end("RAGFlow助手提问工具", answer)
        return answer

    except (TimeoutError, asyncio.TimeoutError) as e:
        monitor.report_end("RAGFlow助手提问工具", error="knowledge base query timed out after retries")
        return "Error: knowledge base query timed out after retries"
    except ConnectionError as e:
        monitor.report_end("RAGFlow助手提问工具", error="knowledge base service unavailable after retries")
        return "Error: knowledge base service unavailable after retries"
    except Exception as e:
        monitor.report_end("RAGFlow助手提问工具", error=str(e))
        return f"提问过程失败：{str(e)}"
    finally:
        if session and hasattr(session, "id") and chat is not None:
            try:
                asyncio.run(_ragflow_delete_sessions(chat, [session.id]))
            except Exception as e:
                logger.warning(f"Failed to delete RAGFlow session: {e}")
