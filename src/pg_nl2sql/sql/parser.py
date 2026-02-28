"""SQL parsing helpers backed by SQLGlot."""

from __future__ import annotations

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


class SQLParseError(RuntimeError):
    """Raised when SQL cannot be parsed safely."""


def parse_postgres_sql(sql: str) -> exp.Expression:
    """Parse a SQL statement using PostgreSQL dialect semantics."""
    normalized = sql.strip()
    if not normalized:
        raise SQLParseError("SQL cannot be empty.")

    try:
        return parse_one(normalized, read="postgres")
    except ParseError as exc:
        raise SQLParseError(f"Invalid SQL: {exc}") from exc
