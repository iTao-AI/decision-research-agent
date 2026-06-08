"""Tests for agent/token_tracking.py — TokenUsageData, TokenUsageCollector, TokenTrackingCallbackHandler"""
import pytest
from unittest.mock import MagicMock
from agent.token_tracking import (
    TokenUsageData, TokenUsageCollector, TokenTrackingCallbackHandler,
    _calculate_cost,
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


class TestTokenPricing:
    def test_deepseek_v4_pro_cost_uses_default_pricing(self):
        """默认成本估算应覆盖当前 DeepSeek V4 Pro 模型名。"""
        cost = _calculate_cost("deepseek-v4-pro", prompt_tokens=1000, completion_tokens=1000)

        assert abs(cost - 0.001305) < 0.000001


class TestTokenTrackingCallbackHandler:
    def test_on_llm_end_from_usage_metadata(self):
        """从 AIMessage.usage_metadata 提取 token（langchain_core >= 0.3 标准路径）"""
        from langchain_core.outputs import LLMResult, ChatGeneration
        from langchain_core.messages import AIMessage

        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        msg = AIMessage(
            content="test response",
            usage_metadata={"input_tokens": 150, "output_tokens": 75, "total_tokens": 225}
        )
        gen = ChatGeneration(message=msg)
        result = LLMResult(generations=[[gen]])

        handler.on_llm_end(result)

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 1
        assert summary["total_prompt"] == 150
        assert summary["total_completion"] == 75

    def test_on_llm_end_from_llm_output(self):
        """从 llm_output.token_usage 提取 token（旧版 provider 兼容路径）"""
        from langchain_core.outputs import LLMResult, ChatGeneration
        from langchain_core.messages import AIMessage

        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        msg = AIMessage(content="test")  # no usage_metadata
        gen = ChatGeneration(message=msg)
        result = LLMResult(
            generations=[[gen]],
            llm_output={"token_usage": {"prompt_tokens": 1000, "completion_tokens": 500}}
        )

        handler.on_llm_end(result)

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 1
        assert summary["total_prompt"] == 1000
        assert summary["total_completion"] == 500
        # qwen-max: prompt ¥0.04/1K, completion ¥0.12/1K
        expected_cost = (1000 / 1000) * 0.04 + (500 / 1000) * 0.12  # = 0.04 + 0.06 = 0.10
        assert abs(summary["total_cost"] - 0.10) < 0.001

    def test_on_llm_end_no_tokens_silent(self):
        """响应无 token 信息时应静默跳过"""
        from langchain_core.outputs import LLMResult, ChatGeneration
        from langchain_core.messages import AIMessage

        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        msg = AIMessage(content="test")  # no usage_metadata
        gen = ChatGeneration(message=msg)
        result = LLMResult(generations=[[gen]])  # no llm_output

        handler.on_llm_end(result)  # 不应抛异常

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 0

    def test_on_llm_end_empty_generations_silent(self):
        """空 generations 时应静默跳过"""
        from langchain_core.outputs import LLMResult

        collector = TokenUsageCollector()
        handler = TokenTrackingCallbackHandler(collector=collector, thread_id="thread-1")

        result = LLMResult(generations=[])
        handler.on_llm_end(result)

        summary = collector.get_summary("thread-1")
        assert summary["call_count"] == 0
