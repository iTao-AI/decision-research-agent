"""Phase 3: SharedContext — 基于 in-memory 的跨 Agent 事实共享层

每个 thread_id 有独立的事实列表，通过显式 thread_id 参数实现隔离。
支持事实发布、查询、去重、容量控制和 session 清理。
"""
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Fact:
    """单条事实记录"""
    fact: str
    source: str
    topic: str
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "fact": self.fact,
            "source": self.source,
            "topic": self.topic,
            "timestamp": self.timestamp,
        }


class SharedContext:
    """跨 Agent 事实共享上下文。

    使用 in-memory dict 存储，以 thread_id 为 key 实现隔离。
    不依赖 ContextVar（由调用方通过 thread_id 显式访问）。
    """

    DEFAULT_MAX_FACTS = 100

    def __init__(self, max_facts: int = DEFAULT_MAX_FACTS):
        self._max_facts = max_facts
        self._facts: dict[str, list[Fact]] = {}

    def publish_fact(
        self,
        thread_id: str,
        fact: str,
        source: str,
        topic: Optional[str] = None,
    ) -> dict:
        """发布事实到指定 thread_id 的共享上下文。

        去重规则：相同 fact + source 不重复写入。
        容量控制：超过上限时 oldest-first 淘汰。
        返回事实的 dict 表示。
        """
        if topic is None:
            topic = source

        facts_list = self._facts.setdefault(thread_id, [])

        # Dedup: same fact + source already exists
        for existing in facts_list:
            if existing.fact == fact and existing.source == source:
                return existing.to_dict()

        new_fact = Fact(fact=fact, source=source, topic=topic, timestamp=time.time())
        facts_list.append(new_fact)

        # Evict oldest if over capacity
        while len(facts_list) > self._max_facts:
            facts_list.pop(0)

        return new_fact.to_dict()

    def query_facts(
        self,
        thread_id: str,
        topic: str,
        source_filter: Optional[str] = None,
    ) -> list[dict]:
        """按 topic 查询事实，可选按 source 过滤。

        空 thread_id 或不存在的 topic 返回空列表。
        """
        facts_list = self._facts.get(thread_id, [])
        results = []
        for f in facts_list:
            if f.topic != topic:
                continue
            if source_filter is not None and f.source != source_filter:
                continue
            results.append(f.to_dict())
        return results

    def clear_facts(self, thread_id: str) -> None:
        """清理指定 thread_id 的所有事实。

        不存在的 thread_id 静默处理。
        """
        self._facts.pop(thread_id, None)
