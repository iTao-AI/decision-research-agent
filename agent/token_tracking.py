"""Token usage tracking for LLM calls."""
from dataclasses import dataclass, field
import os
import json

from langchain_core.callbacks.base import BaseCallbackHandler


# Default pricing: ¥ per 1K tokens
DEFAULT_PRICING = {
    "qwen-max": {"prompt": 0.04, "completion": 0.12},
}


def _load_pricing() -> dict:
    pricing_env = os.getenv("TOKEN_PRICING_JSON")
    if pricing_env:
        try:
            return json.loads(pricing_env)
        except json.JSONDecodeError:
            pass
    return DEFAULT_PRICING


PRICING = _load_pricing()


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    model_pricing = PRICING.get(model, PRICING.get("qwen-max", {"prompt": 0.04, "completion": 0.12}))
    prompt_cost = (prompt_tokens / 1000) * model_pricing["prompt"]
    completion_cost = (completion_tokens / 1000) * model_pricing["completion"]
    return prompt_cost + completion_cost


@dataclass
class TokenUsageData:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = field(init=False)
    model: str = "unknown"
    cost: float = 0.0

    def __post_init__(self):
        self.total_tokens = self.prompt_tokens + self.completion_tokens


class TokenUsageCollector:
    def __init__(self, max_capacity: int = 1000):
        self._records: dict[str, list[TokenUsageData]] = {}
        self._max_capacity = max_capacity

    def record(self, thread_id: str, usage: TokenUsageData) -> None:
        if thread_id not in self._records:
            self._records[thread_id] = []
        self._records[thread_id].append(usage)

        if len(self._records[thread_id]) > self._max_capacity:
            self._records[thread_id].pop(0)

    def get_summary(self, thread_id: str) -> dict:
        records = self._records.get(thread_id, [])
        if not records:
            return {
                "total_prompt": 0, "total_completion": 0,
                "total_tokens": 0, "total_cost": 0.0, "call_count": 0
            }

        return {
            "total_prompt": sum(r.prompt_tokens for r in records),
            "total_completion": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_cost": sum(r.cost for r in records),
            "call_count": len(records),
        }

    def clear_thread(self, thread_id: str) -> None:
        self._records.pop(thread_id, None)


# Global singleton
token_collector = TokenUsageCollector()


class TokenTrackingCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that records token usage per thread."""

    def __init__(self, collector: TokenUsageCollector = None, thread_id: str = None):
        self._collector = collector or token_collector
        self._thread_id = thread_id or "default"

    def on_llm_end(self, response, **kwargs) -> None:
        token_usage = getattr(response, "token_usage", None)
        if token_usage is None:
            return

        prompt_tokens = getattr(token_usage, "prompt_tokens", 0)
        completion_tokens = getattr(token_usage, "completion_tokens", 0)
        model = getattr(response, "model_name", "unknown") or "unknown"
        cost = _calculate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsageData(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
            cost=cost,
        )
        self._collector.record(self._thread_id, usage)
