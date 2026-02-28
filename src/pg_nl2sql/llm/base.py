"""Provider-independent LLM interface for SQL generation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pg_nl2sql.models.generation import SQLGenerationResult
from pg_nl2sql.prompts.sql_generation import PromptBundle


class LLMError(RuntimeError):
    """Raised when LLM generation fails or returns invalid output."""


class LLMGenerator(ABC):
    """Abstract LLM adapter interface."""

    @abstractmethod
    def generate_sql(self, prompt: PromptBundle) -> SQLGenerationResult:
        """Generate structured SQL payload for a prompt bundle."""
