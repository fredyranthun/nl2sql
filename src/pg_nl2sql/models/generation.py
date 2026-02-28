"""Typed generation payload returned by LLM adapters."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SQLGenerationResult(BaseModel):
    """Structured NL-to-SQL generation output contract."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
