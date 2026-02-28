"""LLM adapters and factory helpers."""

from pg_nl2sql.config import Settings
from pg_nl2sql.llm.base import LLMError, LLMGenerator
from pg_nl2sql.llm.openai_adapter import OpenAIAdapter


def create_llm_generator(settings: Settings) -> LLMGenerator:
    """Create default LLM generator for current settings."""
    return OpenAIAdapter(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )


__all__ = [
    "LLMError",
    "LLMGenerator",
    "OpenAIAdapter",
    "create_llm_generator",
]
