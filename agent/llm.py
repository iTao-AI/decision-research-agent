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

from agent.deepseek_chat_model import (
    DeepSeekThinkingChatModel,
    canonical_deepseek_extra_body,
    deepseek_thinking_mode,
    normalize_deepseek_thinking_mode,
)
from agent.provider_observability import (
    PROVIDER_PROTOCOL,
    emit_fallback_activated,
    emit_provider_selected,
)

load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "deepseek-v4-pro"
DEFAULT_LLM_FALLBACK_MODEL = "deepseek-v4-flash"
DEFAULT_REASONING_EFFORT = "max"
DEFAULT_THINKING_MODE = "enabled"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0

_DEEPSEEK_V4_PREFIX = "deepseek-v4-"
_DEEPSEEK_V4_FAMILY = "deepseek-v4"
_DEEPSEEK_PREFIX = "deepseek-"


def _model_name(model: BaseChatModel) -> str:
    value = getattr(model, "model_name", None) or getattr(model, "model", None)
    return str(value or model.__class__.__name__)


def _tool_choice_kind(tool_choice: dict | str | bool | None) -> str | None:
    if tool_choice is None or tool_choice is False:
        return None
    if isinstance(tool_choice, str):
        normalized = tool_choice.lower()
        if normalized == "auto":
            return "automatic"
        if normalized == "none":
            return "none"
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
    return deepseek_thinking_mode(
        getattr(model, "extra_body", None)
    ) == "enabled"


def _needs_tool_choice_compatibility(
    model: BaseChatModel,
    tool_choice: dict | str | bool | None,
) -> bool:
    return (
        _tool_choice_kind(tool_choice) not in {None, "automatic"}
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

    compatible_extra_body = canonical_deepseek_extra_body(
        copy.deepcopy(extra_body)
    )
    compatible_extra_body["thinking"] = {"type": "disabled"}

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
        omit_automatic_deepseek_choice = (
            tool_choice_kind == "automatic"
            and _is_deepseek_v4_model(_model_name(bind_target))
            and _has_enabled_thinking(bind_target)
        )
        if (
            tool_choice is not None
            and tool_choice is not False
            and not omit_automatic_deepseek_choice
        ):
            bind_kwargs["tool_choice"] = tool_choice
        return bind_target.bind_tools(tools, **bind_kwargs)


class FallbackRunnable(Runnable):
    """Runnable fallback wrapper with bounded failure observability."""

    def __init__(
        self,
        primary: Runnable,
        fallback: Runnable,
        primary_provider_family: str,
        fallback_provider_family: str,
    ):
        self.primary = primary
        self.fallback = fallback
        self.primary_provider_family = primary_provider_family
        self.fallback_provider_family = fallback_provider_family

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return self.primary.invoke(input, config=config, **kwargs)
        except Exception as exc:
            emit_fallback_activated(
                primary_provider_family=self.primary_provider_family,
                fallback_provider_family=self.fallback_provider_family,
                error=exc,
                binding="tools",
            )
            return self.fallback.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return await self.primary.ainvoke(input, config=config, **kwargs)
        except Exception as exc:
            emit_fallback_activated(
                primary_provider_family=self.primary_provider_family,
                fallback_provider_family=self.fallback_provider_family,
                error=exc,
                binding="tools",
            )
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
        except Exception as exc:
            emit_fallback_activated(
                primary_provider_family=_provider_family(self.primary),
                fallback_provider_family=_provider_family(self.fallback),
                error=exc,
                binding="direct",
            )
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
        except Exception as exc:
            emit_fallback_activated(
                primary_provider_family=_provider_family(self.primary),
                fallback_provider_family=_provider_family(self.fallback),
                error=exc,
                binding="direct",
            )
            return await self.fallback._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        bind_kwargs = dict(kwargs)
        if tool_choice is not None and tool_choice is not False:
            bind_kwargs["tool_choice"] = tool_choice
        primary = self.primary.bind_tools(tools, **bind_kwargs)
        fallback = self.fallback.bind_tools(tools, **bind_kwargs)
        return FallbackRunnable(
            primary=primary,
            fallback=fallback,
            primary_provider_family=_provider_family(self.primary),
            fallback_provider_family=_provider_family(self.fallback),
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


def _is_deepseek_model(model_name: str) -> bool:
    return model_name.lower().startswith(_DEEPSEEK_PREFIX)


def _provider_family(model: BaseChatModel) -> str:
    return (
        "deepseek"
        if _is_deepseek_model(_model_name(model))
        else "openai-compatible"
    )


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


def _configured_thinking_mode(model_name: str) -> str:
    if _is_deepseek_model(model_name):
        return normalize_deepseek_thinking_mode(
            _env_value("LLM_THINKING_MODE")
        )
    value = _thinking_mode(model_name)
    return "enabled" if value is not None else "disabled"


def _deepseek_observability(
    *,
    model_role: str,
    thinking_mode: str,
) -> dict[str, object]:
    return {
        "tags": [
            "provider:deepseek",
            f"model-role:{model_role}",
            f"protocol:{PROVIDER_PROTOCOL}",
        ],
        "metadata": {
            "provider_family": "deepseek",
            "model_role": model_role,
            "provider_protocol": PROVIDER_PROTOCOL,
            "thinking_mode": thinking_mode,
        },
    }


def _model_kwargs(
    model_name: str,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model_name,
        "callbacks": callbacks or [],
    }

    if _is_deepseek_model(model_name):
        thinking_mode = _configured_thinking_mode(model_name)
        kwargs["timeout"] = DEFAULT_REQUEST_TIMEOUT_SECONDS
        kwargs["extra_body"] = {
            "thinking": {"type": thinking_mode}
        }
        base_url = (
            _env_value("DEEPSEEK_API_BASE")
            or _env_value("OPENAI_BASE_URL")
        )
        api_key = (
            _env_value("DEEPSEEK_API_KEY")
            or _env_value("OPENAI_API_KEY")
        )
    else:
        kwargs["model_provider"] = "openai"
        base_url = _env_value("OPENAI_BASE_URL")
        api_key = _env_value("OPENAI_API_KEY")

    if base_url:
        kwargs["base_url"] = base_url

    if api_key:
        kwargs["api_key"] = api_key

    reasoning_effort = _reasoning_effort(model_name)
    if (
        reasoning_effort
        and reasoning_effort.lower()
        not in {"none", "off", "disabled", "false"}
    ):
        kwargs["reasoning_effort"] = reasoning_effort

    if not _is_deepseek_model(model_name):
        thinking_mode = _thinking_mode(model_name)
        if (
            thinking_mode
            and thinking_mode.lower()
            not in {"none", "off", "disabled", "false"}
        ):
            kwargs["extra_body"] = {
                "thinking": {"type": thinking_mode}
            }

    return kwargs


def _create_leaf_model(
    model_name: str,
    model_role: str,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> BaseChatModel:
    kwargs = _model_kwargs(model_name, callbacks)
    if _is_deepseek_model(model_name):
        thinking_mode = _configured_thinking_mode(model_name)
        kwargs.update(
            _deepseek_observability(
                model_role=model_role,
                thinking_mode=thinking_mode,
            )
        )
        emit_provider_selected(
            model_role=model_role,
            thinking_mode=thinking_mode,
        )
        return DeepSeekThinkingChatModel(
            **kwargs,
            model_role=model_role,
        )
    return init_chat_model(**kwargs)


def create_llm_model(callbacks: list[BaseCallbackHandler] | None = None):
    """Create and return an LLM model with optional callbacks."""
    primary_model = _primary_model_name()
    fallback_model = _fallback_model_name(primary_model)
    primary_role = "primary" if fallback_model else "single"
    primary_observability = (
        _deepseek_observability(
            model_role=primary_role,
            thinking_mode=_configured_thinking_mode(primary_model),
        )
        if _is_deepseek_model(primary_model)
        else {}
    )
    model = CapabilityAwareChatModel(
        wrapped=_create_leaf_model(
            primary_model,
            primary_role,
            callbacks,
        ),
        model_role=primary_role,
        callbacks=callbacks or [],
        **primary_observability,
    )

    if fallback_model and hasattr(model, "with_fallbacks"):
        fallback_observability = (
            _deepseek_observability(
                model_role="fallback",
                thinking_mode=_configured_thinking_mode(fallback_model),
            )
            if _is_deepseek_model(fallback_model)
            else {}
        )
        fallback = CapabilityAwareChatModel(
            wrapped=_create_leaf_model(
                fallback_model,
                "fallback",
                callbacks,
            ),
            model_role="fallback",
            callbacks=callbacks or [],
            **fallback_observability,
        )
        fallback_wrapper_metadata = {
            **dict(primary_observability.get("metadata", {})),
            "fallback_configured": True,
        }
        fallback_wrapper_tags = [
            *list(primary_observability.get("tags", [])),
            "fallback:configured",
        ]
        return FallbackChatModel(
            primary=model,
            fallback=fallback,
            callbacks=callbacks or [],
            metadata=fallback_wrapper_metadata,
            tags=fallback_wrapper_tags,
        )

    return model


# Default model instance (no callbacks for backward compatibility)
model = create_llm_model()
