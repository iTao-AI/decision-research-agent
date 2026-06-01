"""Tavily internet search tool with unified retry and timeout handling."""
import asyncio
import os
from typing import Literal

from langchain_core.tools import tool

from api.context import get_thread_context
from api.monitor import monitor
from tools.retry_utils import TIMEOUTS, retry_async
from tools.cache import cached_tool


async def _tavily_search(
    query: str,
    max_results: int,
    topic: str,
    include_raw_content: bool,
    timeout: int,
) -> dict:
    """Async wrapper around the synchronous Tavily SDK search call.

    Runs the sync TavilyClient.search() in a thread pool executor
    to avoid blocking the event loop, passing the timeout parameter.
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
            timeout=timeout,
        ),
    )
    if result is None:
        return []
    return result


# Cache TTL for Tavily: 5 minutes (300s) — balances API cost savings with result freshness
TAVILY_CACHE_TTL = 300


@cached_tool(ttl=TAVILY_CACHE_TTL, tool_name="tavily_search")
async def _cached_search_with_resilience(
    query: str,
    max_results: int,
    topic: str,
    include_raw_content: bool,
) -> dict:
    """Resilient Tavily search with centralized retry and timeout, cached."""
    timeout = TIMEOUTS["tavily"]
    # Total timeout accounts for: 3 per-call timeouts + 2 backoff waits (2s + 4s = 6s)
    total_timeout = timeout * 3 + 15  # generous budget including backoff
    return await asyncio.wait_for(
        retry_async(
            _tavily_search,
            query,
            max_results,
            topic,
            include_raw_content,
            timeout=timeout,
            max_retries=3,
            service_name="tavily",
        ),
        timeout=total_timeout,
    )


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Search the internet for public information, news, or finance data."""
    thread_id = get_thread_context() or "default"
    return search_with_dedup(
        query,
        search_fn=_internet_search_impl,
        thread_id=thread_id,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )


def _internet_search_impl(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Execute Tavily search without per-thread de-duplication."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY is not configured."

    monitor.report_tool("网络搜索工具", {"网络搜索工具": query})
    try:
        results = asyncio.run(
            _cached_search_with_resilience(query, max_results, topic, include_raw_content)
        )
        monitor.report_end("网络搜索工具", results)
        return results
    except (TimeoutError, asyncio.TimeoutError) as e:
        monitor.report_end("网络搜索工具", error="internet search timed out after 3 retries")
        return "Error: internet search timed out after 3 retries"
    except Exception as e:
        monitor.report_end("网络搜索工具", error=str(e))
        return f"Error: internet search failed after retries — {e}"


# Per-thread search result cache for de-duplication within a task
_search_cache: dict = {}


def _dedup_key(query: str, kwargs: dict) -> tuple:
    return (
        query,
        tuple(sorted((key, repr(value)) for key, value in kwargs.items())),
    )


def search_with_dedup(
    query: str,
    search_fn=None,
    thread_id: str = "default",
    **kwargs,
):
    """Search with deduplication — same query per thread returns cached result.

    Args:
        query: The search query string.
        search_fn: The underlying search function (defaults to internet_search).
        thread_id: Scopes the cache — different threads don't share results.
        **kwargs: Additional arguments passed to the search function.

    Returns:
        Search results (cached or fresh).
    """
    if search_fn is None:
        search_fn = _internet_search_impl

    if thread_id not in _search_cache:
        _search_cache[thread_id] = {}

    cache = _search_cache[thread_id]
    cache_key = _dedup_key(query, kwargs)
    if cache_key in cache:
        monitor.report_cache_hit("tavily_search_dedup", cached=True)
        return cache[cache_key]

    result = search_fn(query, **kwargs)
    cache[cache_key] = result
    return result


def clear_search_cache(thread_id: str = None):
    """Clear the search cache for a thread, or all threads if None."""
    if thread_id:
        _search_cache.pop(thread_id, None)
    else:
        _search_cache.clear()
