from dotenv import load_dotenv, find_dotenv
import os
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler

load_dotenv(find_dotenv())


def create_llm_model(callbacks: list[BaseCallbackHandler] | None = None):
    """Create and return an LLM model with optional callbacks."""
    return init_chat_model(
        model=os.getenv("LLM_QWEN_MAX"),
        model_provider="openai",
        callbacks=callbacks or [],
    )


# Default model instance (no callbacks for backward compatibility)
model = create_llm_model()