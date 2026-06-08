"""Token usage tracking for LLM calls."""
from dataclasses import dataclass, field
import os
import json

from langchain_core.callbacks.base import BaseCallbackHandler


# Default pricing estimate per 1K tokens. Override with TOKEN_PRICING_JSON
# for provider-specific currency, cache-hit pricing, or negotiated rates.
DEFAULT_PRICING = {
    "qwen-max": {"prompt": 0.04, "completion": 0.12},
    "deepseek-chat": {"prompt": 0.001, "completion": 0.002},
    "deepseek-v4-flash": {"prompt": 0.00014, "completion": 0.00028},
    "deepseek-v4-pro": {"prompt": 0.000435, "completion": 0.00087},
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
        """Extract token usage from LLMResult.

        LangChain provides token info through multiple paths depending on the
        provider. We check them in order:
        1. response.generations[0][0].message.usage_metadata (langchain_core >= 0.3)
        2. response.llm_output["token_usage"] (older provider format)
        """
        prompt_tokens = 0
        completion_tokens = 0

        # Path 1: AIMessage.usage_metadata from the generation
        if response.generations:
            try:
                gen = response.generations[0][0]
                message = getattr(gen, "message", None)
                if message:
                    usage_meta = getattr(message, "usage_metadata", None)
                    if usage_meta:
                        if isinstance(usage_meta, dict):
                            prompt_tokens = usage_meta.get("input_tokens", usage_meta.get("prompt_tokens", 0))
                            completion_tokens = usage_meta.get("output_tokens", usage_meta.get("completion_tokens", 0))
                        else:
                            prompt_tokens = getattr(usage_meta, "input_tokens", getattr(usage_meta, "prompt_tokens", 0))
                            completion_tokens = getattr(usage_meta, "output_tokens", getattr(usage_meta, "completion_tokens", 0))
            except (IndexError, AttributeError, TypeError):
                pass

        # Path 2: response.llm_output["token_usage"]
        if prompt_tokens == 0 and completion_tokens == 0:
            llm_output = getattr(response, "llm_output", None) or {}
            token_usage = llm_output.get("token_usage") if isinstance(llm_output, dict) else None
            if token_usage:
                if isinstance(token_usage, dict):
                    prompt_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
                    completion_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0))
                else:
                    prompt_tokens = getattr(token_usage, "prompt_tokens", 0)
                    completion_tokens = getattr(token_usage, "completion_tokens", 0)

        if prompt_tokens == 0 and completion_tokens == 0:
            return

        model = "unknown"
        if hasattr(response, "model_name") and response.model_name:
            model = response.model_name
        elif isinstance(getattr(response, "llm_output", None), dict):
            model = response.llm_output.get("model_name", response.llm_output.get("model", "unknown")) or "unknown"

        cost = _calculate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsageData(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
            cost=cost,
        )
        self._collector.record(self._thread_id, usage)
