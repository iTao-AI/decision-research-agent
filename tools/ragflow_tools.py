"""RAGFlow knowledge base tools with timeout and retry resilience.

All RAGFlow HTTP calls are wrapped with:
- 60-second timeout via concurrent.futures (real thread-level timeout)
- 3 retries with exponential backoff
- Structured error strings for graceful degradation

Note: RAGFlow SDK uses synchronous `requests` without timeout support.
We use a dedicated ThreadPoolExecutor with explicit timeout to ensure
the calling thread is never blocked indefinitely, even if the SDK hangs.
Unlike asyncio.run() which waits for executor shutdown,
concurrent.futures with timeout returns immediately on timeout.
"""
import concurrent.futures
import logging
import os
import time
from typing import Optional, Tuple

from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from api.monitor import monitor
from tools.retry_utils import TIMEOUTS

logger = logging.getLogger(__name__)


def _load_ragflow_env() -> Tuple[Optional[str], Optional[str]]:
    """Load RAGFlow environment variables."""
    return os.getenv("RAGFLOW_API_KEY"), os.getenv("RAGFLOW_API_URL")


def _run_with_timeout(func, timeout: float) -> any:
    """Run a sync function with real thread-level timeout.

    Uses ThreadPoolExecutor with shutdown(wait=False) so that on timeout,
    the caller returns immediately without waiting for the blocked thread.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func)
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"operation timed out after {timeout}s")
    finally:
        executor.shutdown(wait=False)


def _retry_with_timeout(func, max_retries: int = 3, service_name: str = "ragflow") -> any:
    """Sync retry with real thread-level timeout via concurrent.futures.

    Unlike asyncio.wait_for + asyncio.run(), this uses a dedicated
    ThreadPoolExecutor with future.result(timeout=...) and shutdown(wait=False)
    which returns immediately on timeout without waiting for the executor thread.

    Important: on TimeoutError we do NOT retry. Retrying after timeout would
    leave behind blocked threads from each attempt (up to max_retries leaked
    threads). Timeout is treated as a terminal failure.
    """
    timeout = TIMEOUTS["ragflow"]
    backoff_factor = 2
    max_wait = 30
    last_error = None

    for attempt in range(max_retries):
        try:
            return _run_with_timeout(func, timeout)
        except TimeoutError:
            # Don't retry after timeout — each retry would leave a leaked thread.
            raise TimeoutError(f"{service_name} timed out after {timeout}s")
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = min((2 ** attempt) * backoff_factor, max_wait)
                logger.warning(f"[{service_name}] Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"[{service_name}] All {max_retries} attempts failed. Last error: {e}")

    raise last_error


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
        def _do_list():
            rag = RAGFlow(api_key=api_key, base_url=base_url)
            return rag.list_chats()

        assistants = _retry_with_timeout(_do_list, service_name="ragflow-list")

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

    except TimeoutError:
        monitor.report_end("RAGFlow助手列表查询", error="knowledge base query timed out after retries")
        return "Error: knowledge base query timed out after retries"
    except (ConnectionError, OSError) as e:
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
    try:
        # Step 1: Find the chat
        def _find_chat():
            rag = RAGFlow(api_key=api_key, base_url=base_url)
            chats = rag.list_chats(name=assistant_name)
            return chats[0] if chats else None

        chat = _retry_with_timeout(_find_chat, service_name="ragflow-find-chat")
        if chat is None:
            monitor.report_end("RAGFlow助手提问工具", error=f"未找到助手: {assistant_name}")
            return f"没有找到name:{assistant_name}的聊天助手！"

        # Step 2: Create a temporary session
        def _create_session():
            return chat.create_session(name="temp_session")

        session = _retry_with_timeout(_create_session, service_name="ragflow-create-session")

        # Step 3: Ask the question
        def _consume_stream():
            response_stream = session.ask(question=question, stream=True)
            full_answer = ''
            for response in response_stream:
                if hasattr(response, "content") and response.content:
                    full_answer = response.content
            return full_answer

        full_answer = _retry_with_timeout(_consume_stream, service_name="ragflow-ask")

        monitor.report_tool(
            "RAGFlow助手回答记录",
            {"助手名称": assistant_name, "问题": question, "答案": full_answer}
        )
        monitor.report_end("RAGFlow助手提问工具", full_answer)
        return full_answer

    except TimeoutError:
        monitor.report_end("RAGFlow助手提问工具", error="knowledge base query timed out after retries")
        return "Error: knowledge base query timed out after retries"
    except (ConnectionError, OSError) as e:
        monitor.report_end("RAGFlow助手提问工具", error="knowledge base service unavailable after retries")
        return f"Error: knowledge base service unavailable after retries"
    except Exception as e:
        monitor.report_end("RAGFlow助手提问工具", error=str(e))
        return f"提问过程失败：{str(e)}"
    finally:
        if session and hasattr(session, "id") and chat is not None:
            try:
                # Best-effort cleanup with its own timeout
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(lambda: chat.delete_sessions(ids=[session.id]))
                    future.result(timeout=10)
                except concurrent.futures.TimeoutError:
                    executor.shutdown(wait=False)
                    logger.warning("RAGFlow session cleanup timed out")
                finally:
                    executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"Failed to delete RAGFlow session: {e}")
