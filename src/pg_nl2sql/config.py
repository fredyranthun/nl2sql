"""Application configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigError(ValueError):
    """Raised when configuration cannot be loaded safely."""


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    model_config = ConfigDict(frozen=True)

    postgres_dsn: str = Field(min_length=1)
    openai_api_key: str = ""
    openai_model: str = "gpt-5.2-mini"
    schema_cache_path: Path = Path("./data/schema_cache.json")
    default_schema: str = "public"

    @field_validator("postgres_dsn")
    @classmethod
    def validate_postgres_dsn(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("postgresql://", "postgres://")):
            raise ValueError(
                "POSTGRES_DSN must start with 'postgresql://' or 'postgres://'."
            )
        return normalized

    @field_validator("openai_model", "default_schema")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be empty.")
        return normalized

    @field_validator("schema_cache_path", mode="before")
    @classmethod
    def validate_schema_cache_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser() if isinstance(value, str) else value
        if not str(path):
            raise ValueError("SCHEMA_CACHE_PATH cannot be empty.")
        return path

    @property
    def schema_cache_dir(self) -> Path:
        return self.schema_cache_path.parent

    def validate_llm_requirements(self) -> None:
        """Fail with a friendly message when LLM credentials are required."""
        if not self.openai_api_key.strip():
            raise ConfigError(
                "OPENAI_API_KEY is required for SQL generation commands."
            )


def _env_value(name: str, default: str | None = None) -> str | None:
    import os

    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


def load_settings() -> Settings:
    """Load settings from environment variables."""
    payload = {
        "postgres_dsn": _env_value("POSTGRES_DSN"),
        "openai_api_key": _env_value("OPENAI_API_KEY", ""),
        "openai_model": _env_value("OPENAI_MODEL", "gpt-5.2-mini"),
        "schema_cache_path": _env_value("SCHEMA_CACHE_PATH", "./data/schema_cache.json"),
        "default_schema": _env_value("DEFAULT_SCHEMA", "public"),
    }

    if not payload["postgres_dsn"]:
        raise ConfigError(
            "Missing required environment variable: POSTGRES_DSN.\n"
            "Example: postgresql://readonly_user:password@localhost:5432/app_db"
        )

    try:
        return Settings.model_validate(payload)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            field = ".".join(str(item) for item in err["loc"])
            messages.append(f"- {field}: {err['msg']}")
        raise ConfigError(
            "Invalid configuration values:\n" + "\n".join(messages)
        ) from exc
