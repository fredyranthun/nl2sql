"""SQL safety rules for pg-nl2sql validation."""

from __future__ import annotations

from sqlglot import exp

def _optional_exp(name: str) -> type[exp.Expression] | None:
    candidate = getattr(exp, name, None)
    if isinstance(candidate, type) and issubclass(candidate, exp.Expression):
        return candidate
    return None


_FORBIDDEN_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Alter",
    "Create",
    # sqlglot renamed this node in newer versions.
    "Truncate",
    "TruncateTable",
    "Grant",
    "Revoke",
    "Command",
)

FORBIDDEN_STATEMENT_TYPES: tuple[type[exp.Expression], ...] = tuple(
    statement_type
    for statement_type in (_optional_exp(name) for name in _FORBIDDEN_NAMES)
    if statement_type is not None
)

ALLOWED_QUERY_ROOT_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Query,
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
)

DEFAULT_NON_AGGREGATE_LIMIT = 100
