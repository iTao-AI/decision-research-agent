"""Tests for official DeepSeek LLM configuration."""
import importlib
import sys
from unittest.mock import patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda


class FakeChatModel(BaseChatModel):
    model_name: str

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
