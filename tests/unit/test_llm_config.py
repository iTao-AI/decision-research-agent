"""Tests for official DeepSeek LLM configuration."""
import importlib
import sys
from typing import Any
from unittest.mock import patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
import pytest
from pydantic import Field


class FakeChatModel(BaseChatModel):
    model_name: str
    extra_body: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    bind_calls: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.model_name))])


class FailingChatModel(FakeChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("primary failed")


class ToolBindingChatModel(FakeChatModel):
    fail_bound: bool = False

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        self.bind_calls.append(
            {
                "tools": tools,
                "tool_choice": tool_choice,
                "kwargs": kwargs,
                "extra_body": self.extra_body,
                "model_name": self.model_name,
            }
        )

        def _run(_input):
            if self.fail_bound:
                raise RuntimeError(f"{self.model_name} bound failed")
            return AIMessage(content=f"{self.model_name} bound")

        return RunnableLambda(_run)


def _reload_llm(monkeypatch, env: dict[str, str]):
    for key in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LLM_MODEL",
        "LLM_FALLBACK_MODEL",
        "LLM_QWEN_MAX",
        "LLM_REASONING_EFFORT",
        "LLM_THINKING_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    calls = []

    def fake_init_chat_model(**kwargs):
        calls.append(kwargs)
        return FakeChatModel(model_name=kwargs["model"])

    with (
        patch("dotenv.find_dotenv", return_value=""),
        patch("dotenv.load_dotenv", return_value=False),
        patch("langchain.chat_models.init_chat_model", side_effect=fake_init_chat_model),
    ):
        if "agent.llm" in sys.modules:
            llm = importlib.reload(sys.modules["agent.llm"])
        else:
            llm = importlib.import_module("agent.llm")

    return llm, calls


def test_default_model_uses_deepseek_v4_pro_with_flash_fallback(monkeypatch):
    llm, calls = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
        },
    )

    assert [call["model"] for call in calls] == ["deepseek-v4-pro", "deepseek-v4-flash"]
    for call in calls:
        assert call["model_provider"] == "openai"
        assert call["api_key"] == "test-key"
        assert call["base_url"] == "https://api.deepseek.com"
        assert call["reasoning_effort"] == "max"
        assert call["extra_body"] == {"thinking": {"type": "enabled"}}

    assert isinstance(llm.model, BaseChatModel)
    assert llm.model.primary.model_name == "deepseek-v4-pro"
    assert llm.model.fallback.model_name == "deepseek-v4-flash"
    assert isinstance(llm.model.primary, llm.CapabilityAwareChatModel)
    assert isinstance(llm.model.fallback, llm.CapabilityAwareChatModel)


def test_callbacks_are_attached_to_primary_and_fallback(monkeypatch):
    llm, calls = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
        },
    )
    calls.clear()

    callbacks = [BaseCallbackHandler()]
    model = llm.create_llm_model(callbacks=callbacks)

    assert model.primary.model_name == "deepseek-v4-pro"
    assert model.callbacks == callbacks
    assert model.primary.callbacks == callbacks
    assert model.fallback.callbacks == callbacks
    assert [call["callbacks"] for call in calls] == [callbacks, callbacks]


def test_llm_model_overrides_legacy_qwen_env(monkeypatch):
    _, calls = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "LLM_QWEN_MAX": "deepseek-chat",
            "LLM_MODEL": "deepseek-v4-pro",
        },
    )

    assert calls[0]["model"] == "deepseek-v4-pro"


def test_legacy_qwen_env_is_still_supported_when_llm_model_missing(monkeypatch):
    _, calls = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "LLM_QWEN_MAX": "deepseek-chat",
        },
    )

    assert calls[0]["model"] == "deepseek-chat"
    assert "reasoning_effort" not in calls[0]
    assert "extra_body" not in calls[0]
    assert calls[1]["model"] == "deepseek-v4-flash"
    assert calls[1]["reasoning_effort"] == "max"


def test_fallback_chat_model_invokes_fallback_after_primary_failure(monkeypatch):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    model = llm.FallbackChatModel(
        primary=FailingChatModel(model_name="primary"),
        fallback=FakeChatModel(model_name="fallback"),
    )

    response = model.invoke("hello")

    assert response.content == "fallback"


def test_fallback_chat_model_logs_primary_failure(monkeypatch, caplog):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    model = llm.FallbackChatModel(
        primary=FailingChatModel(model_name="primary"),
        fallback=FakeChatModel(model_name="fallback"),
    )

    with caplog.at_level("WARNING"):
        response = model.invoke("hello")

    assert response.content == "fallback"
    assert "Primary LLM failed; falling back to fallback model" in caplog.text


def test_bind_tools_preserves_logged_fallback_path(monkeypatch, caplog):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    model = llm.FallbackChatModel(
        primary=ToolBindingChatModel(model_name="primary", fail_bound=True),
        fallback=ToolBindingChatModel(model_name="fallback"),
    )

    bound = model.bind_tools([])

    with caplog.at_level("WARNING"):
        response = bound.invoke("hello")

    assert response.content == "fallback bound"
    assert "Primary LLM failed after tool binding; falling back to fallback model" in caplog.text


@pytest.mark.parametrize(
    "tool_choice",
    [True, "any", "required", "submit_packet", {"type": "function", "function": {"name": "submit_packet"}}],
)
def test_forced_tool_choice_disables_thinking_on_independent_copy(monkeypatch, tool_choice):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    original_extra_body = {
        "thinking": {"type": "enabled"},
        "provider_option": {"nested": "preserved"},
    }
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body=original_extra_body,
    )
    model = llm.CapabilityAwareChatModel(
        wrapped=leaf,
        model_role="single",
        callbacks=[BaseCallbackHandler()],
    )

    model.bind_tools(["tool"], tool_choice=tool_choice, strict=True)

    assert original_extra_body == {
        "thinking": {"type": "enabled"},
        "provider_option": {"nested": "preserved"},
    }

    compatible_leaf = model.last_bound_model
    assert compatible_leaf is not leaf
    assert compatible_leaf.bind_calls[-1]["tool_choice"] == tool_choice
    assert compatible_leaf.bind_calls[-1]["kwargs"] == {"strict": True}
    assert compatible_leaf.extra_body == {
        "thinking": {"type": "disabled"},
        "provider_option": {"nested": "preserved"},
    }


@pytest.mark.parametrize("tool_choice", [None, False, "none", "auto"])
def test_non_forced_tool_choice_preserves_thinking_on_original_model(monkeypatch, tool_choice):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    if tool_choice is None:
        model.bind_tools(["tool"])
    else:
        model.bind_tools(["tool"], tool_choice=tool_choice)

    assert model.last_bound_model is leaf
    assert leaf.bind_calls[-1]["tool_choice"] == tool_choice
    assert leaf.bind_calls[-1]["extra_body"] == {"thinking": {"type": "enabled"}}


def test_fallback_disabled_still_returns_capability_aware_model(monkeypatch):
    llm, _ = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "LLM_FALLBACK_MODEL": "none",
        },
    )

    model = llm.create_llm_model()

    assert isinstance(model, llm.CapabilityAwareChatModel)
    assert model.model_name == "deepseek-v4-pro"


def test_matching_fallback_model_still_returns_capability_aware_model(monkeypatch):
    llm, _ = _reload_llm(
        monkeypatch,
        {
            "OPENAI_API_KEY": "test-key",
            "LLM_FALLBACK_MODEL": "deepseek-v4-pro",
        },
    )

    model = llm.create_llm_model()

    assert isinstance(model, llm.CapabilityAwareChatModel)
    assert model.model_name == "deepseek-v4-pro"


def test_fallback_chat_model_forwards_forced_tool_choice_to_compatible_models(monkeypatch):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    primary_leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}},
    )
    fallback_leaf = ToolBindingChatModel(
        model_name="deepseek-v4-flash",
        extra_body={"thinking": {"type": "enabled"}},
    )
    primary = llm.CapabilityAwareChatModel(wrapped=primary_leaf, model_role="primary")
    fallback = llm.CapabilityAwareChatModel(wrapped=fallback_leaf, model_role="fallback")
    model = llm.FallbackChatModel(primary=primary, fallback=fallback)

    model.bind_tools(["tool"], tool_choice="any")

    assert primary.last_bound_model is not primary_leaf
    assert fallback.last_bound_model is not fallback_leaf
    assert primary.last_bound_model.bind_calls[-1]["tool_choice"] == "any"
    assert fallback.last_bound_model.bind_calls[-1]["tool_choice"] == "any"
    assert primary.last_bound_model.extra_body == {"thinking": {"type": "disabled"}}
    assert fallback.last_bound_model.extra_body == {"thinking": {"type": "disabled"}}


def test_thinking_disabled_model_binds_original_for_forced_tool_choice(monkeypatch):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    model.bind_tools(["tool"], tool_choice="required")

    assert model.last_bound_model is leaf
    assert leaf.bind_calls[-1]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_non_deepseek_v4_model_binds_original_for_forced_tool_choice(monkeypatch):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-chat",
        extra_body={"thinking": {"type": "enabled"}},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    model.bind_tools(["tool"], tool_choice="required")

    assert model.last_bound_model is leaf
    assert leaf.bind_calls[-1]["extra_body"] == {"thinking": {"type": "enabled"}}


def test_capability_wrapper_exposes_wrapped_model_profile(monkeypatch):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        profile={"structured_output": False, "max_input_tokens": 1000},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    assert model.profile == {"structured_output": False, "max_input_tokens": 1000}


def test_capability_adaptation_logs_only_allowlisted_fields(monkeypatch, caplog):
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}, "secret_payload": "do-not-log"},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    with caplog.at_level("INFO"):
        model.bind_tools(["sensitive tool schema"], tool_choice={"secret": "do-not-log"})

    assert "event=model_capability_adaptation" in caplog.text
    assert "reason=thinking_forced_tool_choice_conflict" in caplog.text
    assert "model_family=deepseek-v4" in caplog.text
    assert "model_role=single" in caplog.text
    assert "tool_choice_kind=tool_dict" in caplog.text
    assert "configured_thinking_mode=enabled" in caplog.text
    assert "effective_thinking_mode=disabled" in caplog.text
    assert "sensitive tool schema" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_tool_choice_compatible_model_raises_when_model_copy_missing(monkeypatch):
    """_tool_choice_compatible_model must raise TypeError when model lacks model_copy."""
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}},
    )
    # Remove model_copy to simulate a model that doesn't support it
    object.__setattr__(leaf, "model_copy", None)
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    with pytest.raises(TypeError, match="without model_copy support"):
        model.bind_tools(["tool"], tool_choice="required")


@pytest.mark.parametrize("tool_choice", [42, 3.14, [1, 2]])
def test_unsupported_tool_choice_type_raises_typeerror(monkeypatch, tool_choice):
    """Unsupported tool_choice types must raise TypeError, not silently bypass adaptation."""
    llm, _ = _reload_llm(monkeypatch, {"OPENAI_API_KEY": "test-key"})
    leaf = ToolBindingChatModel(
        model_name="deepseek-v4-pro",
        extra_body={"thinking": {"type": "enabled"}},
    )
    model = llm.CapabilityAwareChatModel(wrapped=leaf, model_role="single")

    with pytest.raises(TypeError, match="Unsupported tool_choice type"):
        model.bind_tools(["tool"], tool_choice=tool_choice)
