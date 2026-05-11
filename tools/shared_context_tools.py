"""Phase 3: SharedContext tools — 供子 Agent 调用的事实发布/查询工具"""
from langchain_core.tools import tool

from agent.shared_context import SharedContext

# 延迟初始化：避免模块级 import 触发 main_agent 创建
_context: SharedContext | None = None


def _get_context() -> SharedContext:
    """获取 SharedContext 实例，延迟避免循环依赖"""
    global _context
    if _context is None:
        from agent.main_agent import shared_context
        _context = shared_context
    return _context


def _resolve_thread_id(thread_id: str) -> str:
    """自动从 session 上下文解析 thread_id，避免跨 session 事实泄漏"""
    if thread_id:
        return thread_id
    try:
        from api.context import get_thread_context
        tid = get_thread_context()
        return tid if tid else "default"
    except Exception:
        return "default"


@tool
def publish_fact(fact: str, source: str, topic: str = "", thread_id: str = "") -> str:
    """Publish a fact to the shared context for other agents to see."""
    try:
        ctx = _get_context()
        result = ctx.publish_fact(
            thread_id=_resolve_thread_id(thread_id),
            fact=fact,
            source=source,
            topic=topic or source,
        )
        return f"事实已发布: {result['fact']} (topic: {result['topic']})"
    except Exception as e:
        return f"事实发布失败: {e}"


@tool
def query_facts(topic: str, source_filter: str = "", thread_id: str = "") -> str:
    """Query facts from the shared context by topic."""
    try:
        ctx = _get_context()
        results = ctx.query_facts(
            thread_id=_resolve_thread_id(thread_id),
            topic=topic,
            source_filter=source_filter or None,
        )
        if not results:
            return f"主题 '{topic}' 下没有找到事实"
        lines = [f"- {r['fact']} (source: {r['source']})" for r in results]
        return f"主题 '{topic}' 下找到 {len(results)} 条事实:\n" + "\n".join(lines)
    except Exception as e:
        return f"事实查询失败: {e}"
