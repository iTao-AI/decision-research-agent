"""Phase 3: SharedContext 单元测试 — 事实发布、查询、去重、容量控制、清理"""
import pytest
import time
from agent.shared_context import SharedContext


class TestSharedContextPublish:
    """测试事实发布"""

    def setup_method(self):
        self.ctx = SharedContext()

    def test_publish_single_fact(self):
        """发布单条事实应成功"""
        result = self.ctx.publish_fact(
            thread_id="t1",
            fact="某公司2024年营收100亿",
            source="network_search",
            topic="company_revenue"
        )
        assert result["fact"] == "某公司2024年营收100亿"
        assert result["source"] == "network_search"
        assert result["topic"] == "company_revenue"
        assert "timestamp" in result

    def test_publish_fact_auto_topic(self):
        """未提供 topic 时应从 source 派生"""
        result = self.ctx.publish_fact(
            thread_id="t1",
            fact="test fact",
            source="db_query"
        )
        assert result["topic"] == "db_query"

    def test_publish_multiple_facts(self):
        """发布多条事实应全部保留"""
        self.ctx.publish_fact(thread_id="t1", fact="fact1", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t1", fact="fact2", source="s2", topic="t")
        self.ctx.publish_fact(thread_id="t1", fact="fact3", source="s1", topic="t")
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 3

    def test_publish_dedup_same_fact_and_source(self):
        """相同 fact + source 应去重，不重复写入"""
        r1 = self.ctx.publish_fact(thread_id="t1", fact="same", source="s1", topic="t")
        r2 = self.ctx.publish_fact(thread_id="t1", fact="same", source="s1", topic="t")
        assert r1 == r2
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 1

    def test_publish_no_dedup_different_source(self):
        """相同 fact 但不同 source 不应去重"""
        self.ctx.publish_fact(thread_id="t1", fact="same", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t1", fact="same", source="s2", topic="t")
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 2

    def test_publish_no_dedup_different_fact(self):
        """相同 source 但不同 fact 不应去重"""
        self.ctx.publish_fact(thread_id="t1", fact="a", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t1", fact="b", source="s1", topic="t")
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 2


class TestSharedContextQuery:
    """测试事实查询"""

    def setup_method(self):
        self.ctx = SharedContext()
        self.ctx.publish_fact(thread_id="t1", fact="f1", source="network_search", topic="search")
        self.ctx.publish_fact(thread_id="t1", fact="f2", source="db_query", topic="db")
        self.ctx.publish_fact(thread_id="t1", fact="f3", source="network_search", topic="db")

    def test_query_by_topic(self):
        """按主题查询应返回匹配事实"""
        results = self.ctx.query_facts(thread_id="t1", topic="search")
        assert len(results) == 1
        assert results[0]["fact"] == "f1"

    def test_query_by_topic_and_source(self):
        """按主题 + 来源过滤应返回精确匹配"""
        results = self.ctx.query_facts(thread_id="t1", topic="db", source_filter="network_search")
        assert len(results) == 1
        assert results[0]["fact"] == "f3"

    def test_query_unknown_topic(self):
        """查询不存在的 topic 应返回空列表"""
        results = self.ctx.query_facts(thread_id="t1", topic="nonexistent")
        assert results == []

    def test_query_empty_state(self):
        """空状态下查询应返回空列表不报错"""
        ctx = SharedContext()
        results = ctx.query_facts(thread_id="t1", topic="anything")
        assert results == []

    def test_query_no_filter_returns_all_for_topic(self):
        """不带 source_filter 应返回该 topic 下所有事实"""
        results = self.ctx.query_facts(thread_id="t1", topic="db")
        assert len(results) == 2


class TestSharedContextIsolation:
    """测试线程隔离（不同 thread_id 互不干扰）"""

    def setup_method(self):
        self.ctx = SharedContext()

    def test_different_thread_ids_isolated(self):
        """不同 thread_id 发布的事实应完全隔离"""
        self.ctx.publish_fact(thread_id="t1", fact="t1_fact", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t2", fact="t2_fact", source="s1", topic="t")

        t1_facts = self.ctx.query_facts(thread_id="t1", topic="t")
        t2_facts = self.ctx.query_facts(thread_id="t2", topic="t")

        assert len(t1_facts) == 1
        assert t1_facts[0]["fact"] == "t1_fact"
        assert len(t2_facts) == 1
        assert t2_facts[0]["fact"] == "t2_fact"

    def test_clear_facts_only_target_thread(self):
        """清理某个 thread_id 不应影响其他 thread_id"""
        self.ctx.publish_fact(thread_id="t1", fact="t1_fact", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t2", fact="t2_fact", source="s1", topic="t")

        self.ctx.clear_facts(thread_id="t1")

        t1_facts = self.ctx.query_facts(thread_id="t1", topic="t")
        t2_facts = self.ctx.query_facts(thread_id="t2", topic="t")

        assert len(t1_facts) == 0
        assert len(t2_facts) == 1


class TestSharedContextCapacity:
    """测试容量控制"""

    def setup_method(self):
        self.ctx = SharedContext(max_facts=5)  # Use small cap for testing

    def test_capacity_limit_evicts_oldest(self):
        """超过容量上限应自动淘汰最早的事实"""
        for i in range(7):
            self.ctx.publish_fact(thread_id="t1", fact=f"fact_{i}", source="s1", topic="t")

        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 5
        # Oldest facts (0, 1) should be evicted
        assert facts[0]["fact"] == "fact_2"
        assert facts[-1]["fact"] == "fact_6"

    def test_capacity_per_thread_id(self):
        """容量限制应按 thread_id 独立计算"""
        for i in range(5):
            self.ctx.publish_fact(thread_id="t1", fact=f"t1_{i}", source="s1", topic="t")
            self.ctx.publish_fact(thread_id="t2", fact=f"t2_{i}", source="s1", topic="t")

        assert len(self.ctx.query_facts(thread_id="t1", topic="t")) == 5
        assert len(self.ctx.query_facts(thread_id="t2", topic="t")) == 5


class TestSharedContextClear:
    """测试清理"""

    def setup_method(self):
        self.ctx = SharedContext()

    def test_clear_facts_removes_all(self):
        """清理应移除指定 thread_id 的所有事实"""
        self.ctx.publish_fact(thread_id="t1", fact="f1", source="s1", topic="t")
        self.ctx.publish_fact(thread_id="t1", fact="f2", source="s1", topic="t")
        self.ctx.clear_facts(thread_id="t1")
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert facts == []

    def test_clear_nonexistent_thread(self):
        """清理不存在的 thread_id 不应报错"""
        self.ctx.clear_facts(thread_id="nonexistent")

    def test_clear_and_republish(self):
        """清理后应可重新发布事实"""
        self.ctx.publish_fact(thread_id="t1", fact="old", source="s1", topic="t")
        self.ctx.clear_facts(thread_id="t1")
        self.ctx.publish_fact(thread_id="t1", fact="new", source="s1", topic="t")
        facts = self.ctx.query_facts(thread_id="t1", topic="t")
        assert len(facts) == 1
        assert facts[0]["fact"] == "new"
