from dotenv import load_dotenv, find_dotenv
import copy
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

_DEEPSEEK_V4_PREFIX = "deepseek-v4-"
_DEEPSEEK_V4_FAMILY = "deepseek-v4"


def _model_name(model: BaseChatModel) -> str:
    value = getattr(model, "model_name", None) or getattr(model, "model", None)
    return str(value or model.__class__.__name__)


def _tool_choice_kind(tool_choice: dict | str | bool | None) -> str | None:
    if tool_choice is None or tool_choice is False:
        return None
    if isinstance(tool_choice, str):
        normalized = tool_choice.lower()
        if normalized in {"none", "auto"}:
            return None
        if normalized in {"any", "required"}:
            return "required"
        return "tool_name"
    if tool_choice is True:
        return "required"
    if isinstance(tool_choice, dict):
        return "tool_dict"
    raise TypeError(
        f"Unsupported tool_choice type: {type(tool_choice).__name__}. "
        "Expected dict, str, bool, or None."
    )


def _has_enabled_thinking(model: BaseChatModel) -> bool:
    extra_body = getattr(model, "extra_body", None)
    if not isinstance(extra_body, dict):
        return False
    thinking = extra_body.get("thinking")
    if not isinstance(thinking, dict):
        return False
    return str(thinking.get("type", "")).lower() == "enabled"


def _needs_tool_choice_compatibility(
    model: BaseChatModel,
    tool_choice: dict | str | bool | None,
) -> bool:
    return (
        _tool_choice_kind(tool_choice) is not None
        and _is_deepseek_v4_model(_model_name(model))
        and _has_enabled_thinking(model)
    )


def _tool_choice_compatible_model(model: BaseChatModel) -> BaseChatModel:
    extra_body = getattr(model, "extra_body", None)
    # Defensive guard: _has_enabled_thinking already verifies extra_body is a
    # dict before this function is called, so this branch is unreachable via
    # the current bind_tools() path.  Kept as a fail-closed gate in case this
    # helper is ever called directly from outside the capability wrapper.
    if not isinstance(extra_body, dict):
        raise TypeError("Cannot build compatible model without dict extra_body")

    compatible_extra_body = copy.deepcopy(extra_body)
    thinking = compatible_extra_body.get("thinking")
    if not isinstance(thinking, dict):
        thinking = {}
        compatible_extra_body["thinking"] = thinking
    thinking["type"] = "disabled"

    model_copy = getattr(model, "model_copy", None)
    if not callable(model_copy):
        raise TypeError("Cannot build compatible model without model_copy support")
    # deep=False intentionally shares runtime objects (HTTP client, callbacks)
    # between the original and adapted model.  This is safe because bind_tools
    # does not mutate shared state, and concurrent requests through the shared
    # HTTP session are expected.  Do not mutate shared objects on the adapted
    # model without reviewing this contract.
    return model_copy(update={"extra_body": compatible_extra_body}, deep=False)


class CapabilityAwareChatModel(BaseChatModel):
    """Leaf model wrapper that adapts known provider capability conflicts."""

    wrapped: BaseChatModel
    model_role: str = "single"
    # Test-visible only: the model instance used for the most recent
    # bind_tools() call.  Never read in production code paths — do not
    # reference in _generate / _agenerate or any runtime decision.
    last_bound_model: BaseChatModel | None = None
    profile: dict[str, Any] | None = None

    def __init__(self, **data: Any) -> None:
        data = dict(data)  # defensive copy – avoid mutating caller's dict
        if data.get("profile") is None:
            wrapped_profile = getattr(data.get("wrapped"), "profile", None)
            if isinstance(wrapped_profile, dict):
                data["profile"] = wrapped_profile
        super().__init__(**data)

    @property
    def model_name(self) -> str:
        return _model_name(self.wrapped)

    @property
    def _llm_type(self) -> str:
        return f"capability-aware-{self.wrapped._llm_type}"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "wrapped": self.model_name,
            "model_role": self.model_role,
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self.wrapped._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return await self.wrapped._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        bind_target = self.wrapped
        tool_choice_kind = _tool_choice_kind(tool_choice)
        if _needs_tool_choice_compatibility(self.wrapped, tool_choice):
            bind_target = _tool_choice_compatible_model(self.wrapped)
            logger.info(
                "event=model_capability_adaptation "
                "reason=thinking_forced_tool_choice_conflict "
                f"model_family={_DEEPSEEK_V4_FAMILY} "
                "model_role=%s "
                "tool_choice_kind=%s "
                "configured_thinking_mode=enabled "
                "effective_thinking_mode=disabled",
                self.model_role,
                tool_choice_kind,
            )

        self.last_bound_model = bind_target
        bind_kwargs = dict(kwargs)
        if tool_choice is not None:
            bind_kwargs["tool_choice"] = tool_choice
        return bind_target.bind_tools(tools, **bind_kwargs)


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
        tool_choice: dict | str | bool | None = None,
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
    return model_name.startswith(_DEEPSEEK_V4_PREFIX)


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
    model = CapabilityAwareChatModel(
        wrapped=init_chat_model(**_model_kwargs(primary_model, callbacks)),
        model_role="primary",
        callbacks=callbacks or [],
    )

    fallback_model = _fallback_model_name(primary_model)
    if fallback_model and hasattr(model, "with_fallbacks"):
        fallback = CapabilityAwareChatModel(
            wrapped=init_chat_model(**_model_kwargs(fallback_model, callbacks)),
            model_role="fallback",
            callbacks=callbacks or [],
        )
        return FallbackChatModel(primary=model, fallback=fallback, callbacks=callbacks or [])

    model.model_role = "single"
    return model


# Default model instance (no callbacks for backward compatibility)
model = create_llm_model()
