from dotenv import load_dotenv, find_dotenv
import logging
import os
from typing import Any, Sequence

from langchain.chat_models import init_chat_model
from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable

load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "deepseek-v4-pro"
DEFAULT_LLM_FALLBACK_MODEL = "deepseek-v4-flash"
DEFAULT_REASONING_EFFORT = "max"
DEFAULT_THINKING_MODE = "enabled"


class FallbackRunnable(Runnable):
    """Runnable fallback wrapper that logs primary failures."""

    def __init__(self, primary: Runnable, fallback: Runnable, warning_message: str):
        self.primary = primary
        self.fallback = fallback
        self.warning_message = warning_message

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return self.primary.invoke(input, config=config, **kwargs)
        except Exception:
            logger.warning(self.warning_message, exc_info=True)
            return self.fallback.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return await self.primary.ainvoke(input, config=config, **kwargs)
        except Exception:
            logger.warning(self.warning_message, exc_info=True)
            return await self.fallback.ainvoke(input, config=config, **kwargs)


class FallbackChatModel(BaseChatModel):
    """BaseChatModel-compatible primary/fallback wrapper for DeepAgents."""

    primary: BaseChatModel
    fallback: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "primary": getattr(self.primary, "model_name", self.primary.__class__.__name__),
            "fallback": getattr(self.fallback, "model_name", self.fallback.__class__.__name__),
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return self.primary._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception:
            logger.warning("Primary LLM failed; falling back to fallback model", exc_info=True)
            return self.fallback._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await self.primary._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception:
            logger.warning("Primary LLM failed; falling back to fallback model", exc_info=True)
            return await self.fallback._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        bind_kwargs = dict(kwargs)
        if tool_choice is not None:
            bind_kwargs["tool_choice"] = tool_choice
        primary = self.primary.bind_tools(tools, **bind_kwargs)
        fallback = self.fallback.bind_tools(tools, **bind_kwargs)
        return FallbackRunnable(
            primary=primary,
            fallback=fallback,
            warning_message=(
                "Primary LLM failed after tool binding; falling back to fallback model"
            ),
        )


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _primary_model_name() -> str:
    return _env_value("LLM_MODEL") or _env_value("LLM_QWEN_MAX") or DEFAULT_LLM_MODEL


def _fallback_model_name(primary_model: str) -> str | None:
    fallback = _env_value("LLM_FALLBACK_MODEL") or DEFAULT_LLM_FALLBACK_MODEL
    if fallback.lower() in {"none", "off", "disabled", "false"}:
        return None
    if fallback == primary_model:
        return None
    return fallback


def _is_deepseek_v4_model(model_name: str) -> bool:
    return model_name.startswith("deepseek-v4-")


def _reasoning_effort(model_name: str) -> str | None:
    configured = _env_value("LLM_REASONING_EFFORT")
    if configured is not None:
        return configured
    if _is_deepseek_v4_model(model_name):
        return DEFAULT_REASONING_EFFORT
    return None


def _thinking_mode(model_name: str) -> str | None:
    configured = _env_value("LLM_THINKING_MODE")
    if configured is not None:
        return configured
    if _is_deepseek_v4_model(model_name):
        return DEFAULT_THINKING_MODE
    return None


def _model_kwargs(model_name: str, callbacks: list[BaseCallbackHandler] | None = None) -> dict:
    kwargs = {
        "model": model_name,
        "model_provider": "openai",
        "callbacks": callbacks or [],
    }

    base_url = _env_value("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url

    api_key = _env_value("OPENAI_API_KEY")
    if api_key:
        kwargs["api_key"] = api_key

    reasoning_effort = _reasoning_effort(model_name)
    if reasoning_effort and reasoning_effort.lower() not in {"none", "off", "disabled", "false"}:
        kwargs["reasoning_effort"] = reasoning_effort

    thinking_mode = _thinking_mode(model_name)
    if thinking_mode and thinking_mode.lower() not in {"none", "off", "disabled", "false"}:
        kwargs["extra_body"] = {"thinking": {"type": thinking_mode}}

    return kwargs


def create_llm_model(callbacks: list[BaseCallbackHandler] | None = None):
    """Create and return an LLM model with optional callbacks."""
    primary_model = _primary_model_name()
    model = init_chat_model(**_model_kwargs(primary_model, callbacks))

    fallback_model = _fallback_model_name(primary_model)
    if fallback_model and hasattr(model, "with_fallbacks"):
        fallback = init_chat_model(**_model_kwargs(fallback_model, callbacks))
        return FallbackChatModel(primary=model, fallback=fallback, callbacks=callbacks or [])

    return model


# Default model instance (no callbacks for backward compatibility)
model = create_llm_model()
