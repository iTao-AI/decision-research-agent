"""Tests for agent/token_tracking.py — TokenUsageData, TokenUsageCollector, TokenTrackingCallbackHandler"""
import pytest
from unittest.mock import MagicMock
from agent.token_tracking import (
    TokenUsageData, TokenUsageCollector, TokenTrackingCallbackHandler
)


class TestTokenUsageData:
    def test_total_tokens_auto_calculated(self):
        """total_tokens 应自动等于 prompt + completion"""
        usage = TokenUsageData(prompt_tokens=100, completion_tokens=200)
        assert usage.total_tokens == 300

    def test_total_tokens_with_model_and_cost(self):
        """支持 model 和 cost 字段"""
        usage = TokenUsageData(
            prompt_tokens=50, completion_tokens=30,
            model="qwen-max", cost=0.006
        )
        assert usage.total_tokens == 80
        assert usage.model == "qwen-max"
        assert usage.cost == 0.006

    def test_cost_defaults_to_zero(self):
        """未传 cost 时默认为 0"""
        usage = TokenUsageData(prompt_tokens=10, completion_tokens=5)
        assert usage.cost == 0.0

    def test_model_defaults_to_unknown(self):
        """未传 model 时默认为 unknown"""
        usage = TokenUsageData(prompt_tokens=10, completion_tokens=5)
        assert usage.model == "unknown"


class TestTokenUsageCollector:
    def test_record_and_get_summary(self):
        """记录后应能查询汇总"""
        collector = TokenUsageCollector()
        collector.record("thread-1", TokenUsageData(prompt_tokens=100, completion_tokens=50))

        summary = collector.get_summary("thread-1")
        assert summary["total_prompt"] == 100
        assert summary["total_completion"] == 50
        assert summary["total_tokens"] == 150
        assert summary["call_count"] == 1

    def test_accumulates_multiple_records(self):
        """多条记录应累加"""
        collector = TokenUsageCollector()
        collector.record("thread-1", TokenUsageData(prompt_tokens=100, completion_tokens=50))
        collector.record("thread-1", TokenUsageData(prompt_tokens=200, completion_tokens=100))

        summary = collector.get_summary("thread-1")
        assert summary["total_prompt"] == 300
        assert summary["total_completion"] == 150
        assert summary["total_tokens"] == 450
        assert summary["call_count"] == 2

    def test_isolates_by_thread_id(self):
        """不同 thread_id 应独立"""
        collector = TokenUsageCollector()
        collector.record("thread-1", TokenUsageData(prompt_tokens=100, completion_tokens=50))
        collector.record("thread-2", TokenUsageData(prompt_tokens=200, completion_tokens=100))

        s1 = collector.get_summary("thread-1")
        s2 = collector.get_summary("thread-2")
        assert s1["total_prompt"] == 100
        assert s2["total_prompt"] == 200

    def test_nonexistent_thread_returns_zeros(self):
        """不存在的 thread 应返回全零"""
        collector = TokenUsageCollector()
        summary = collector.get_summary("nonexistent")
        assert summary == {
            "total_prompt": 0, "total_completion": 0,
            "total_tokens": 0, "total_cost": 0.0, "call_count": 0
        }

    def test_cost_accumulates(self):
        """cost 应累加"""
        collector = TokenUsageCollector()
        collector.record("thread-1", TokenUsageData(prompt_tokens=100, completion_tokens=50, cost=0.01))
        collector.record("thread-1", TokenUsageData(prompt_tokens=50, completion_tokens=30, cost=0.005))

        summary = collector.get_summary("thread-1")
        assert summary["total_cost"] == 0.015

    def test_capacity_control_evicts_oldest(self):
        """超过 1000 条应淘汰最早的"""
        collector = TokenUsageCollector(max_capacity=5)
        for i in range(7):
            collector.record("thread-1", TokenUsageData(prompt_tokens=10, completion_tokens=5))

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 5

    def test_clear_thread(self):
        """清理后应返回全零"""
        collector = TokenUsageCollector()
        collector.record("thread-1", TokenUsageData(prompt_tokens=100, completion_tokens=50))
        collector.clear_thread("thread-1")
        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 0


class TestTokenTrackingCallbackHandler:
    def test_on_llm_end_records_tokens(self):
        """LLM 调用完成时应记录 token 用量"""
        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        mock_response = MagicMock()
        mock_response.token_usage = MagicMock()
        mock_response.token_usage.prompt_tokens = 150
        mock_response.token_usage.completion_tokens = 75

        handler.on_llm_end(mock_response)

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 1
        assert summary["total_prompt"] == 150
        assert summary["total_completion"] == 75

    def test_on_llm_end_uses_default_pricing(self):
        """应使用默认定价计算成本"""
        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        mock_response = MagicMock()
        mock_response.token_usage = MagicMock()
        mock_response.token_usage.prompt_tokens = 1000
        mock_response.token_usage.completion_tokens = 500

        handler.on_llm_end(mock_response)

        summary = collector.get_summary("thread-1")
        # qwen-max: prompt ¥0.04/1K, completion ¥0.12/1K
        expected_cost = (1000 / 1000) * 0.04 + (500 / 1000) * 0.12  # = 0.04 + 0.06 = 0.10
        assert abs(summary["total_cost"] - 0.10) < 0.001

    def test_on_llm_end_no_token_usage_silent(self):
        """响应无 token_usage 时应静默跳过"""
        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        mock_response = MagicMock()
        mock_response.token_usage = None

        handler.on_llm_end(mock_response)  # 不应抛异常

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 0

    def test_on_llm_end_missing_model_uses_default_pricing(self):
        """未知模型应使用默认定价"""
        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        mock_response = MagicMock()
        mock_response.token_usage = MagicMock()
        mock_response.token_usage.prompt_tokens = 100
        mock_response.token_usage.completion_tokens = 50
        # 不提供 model_name 属性
        del mock_response.model_name

        handler.on_llm_end(mock_response)

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 1
