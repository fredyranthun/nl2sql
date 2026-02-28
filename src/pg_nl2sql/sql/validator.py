"""SQL validation and guardrails for safe NL-to-SQL output."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp

from pg_nl2sql.db.introspect import SchemaSnapshot
from pg_nl2sql.sql.parser import SQLParseError, parse_postgres_sql
from pg_nl2sql.sql.rules import (
    ALLOWED_QUERY_ROOT_TYPES,
    DEFAULT_NON_AGGREGATE_LIMIT,
    FORBIDDEN_STATEMENT_TYPES,
)


class SQLValidationError(RuntimeError):
    """Raised when SQL fails validation guardrails."""


@dataclass(frozen=True)
class SQLValidationResult:
    """Structured SQL validation result."""

    is_valid: bool
    sql: str
    normalized_sql: str
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    limit_added: bool = False


def _allowed_table_map(snapshot: SchemaSnapshot) -> dict[str, set[str]]:
    return {
        schema_name: set(schema.tables.keys())
        for schema_name, schema in snapshot.schemas.items()
    }


def _all_table_names(snapshot: SchemaSnapshot) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for schema_name, schema in snapshot.schemas.items():
        for table_name in schema.tables.keys():
            index.setdefault(table_name, set()).add(schema_name)
    return index


def _cte_names(expression: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in expression.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            names.add(alias)
    return names


def _resolve_table_fqn(
    table: exp.Table,
    snapshot: SchemaSnapshot,
    *,
    default_schema: str,
) -> tuple[str | None, str | None]:
    table_name = table.name
    schema_name = table.db

    if not table_name:
        return None, "Encountered table reference with empty name."

    available = _allowed_table_map(snapshot)
    all_names = _all_table_names(snapshot)

    if schema_name:
        if schema_name in available and table_name in available[schema_name]:
            return f"{schema_name}.{table_name}", None
        return None, f"Table '{schema_name}.{table_name}' is not present in schema cache."

    candidates = sorted(all_names.get(table_name, set()))
    if not candidates:
        return None, f"Table '{table_name}' is not present in schema cache."
    if len(candidates) == 1:
        return f"{candidates[0]}.{table_name}", None
    if default_schema in candidates:
        return f"{default_schema}.{table_name}", None
    return (
        None,
        "Unqualified table reference is ambiguous for "
        f"'{table_name}' across schemas {', '.join(candidates)}.",
    )


def _non_aggregate_query(expression: exp.Expression) -> bool:
    return not any(True for _ in expression.find_all(exp.AggFunc))


def validate_sql(
    sql: str,
    snapshot: SchemaSnapshot,
    *,
    allowed_tables: list[str] | None = None,
    default_schema: str = "public",
    enforce_limit: bool = True,
    default_limit: int = DEFAULT_NON_AGGREGATE_LIMIT,
) -> SQLValidationResult:
    """Validate SQL against safety and schema allowlist guardrails."""
    try:
        expression = parse_postgres_sql(sql)
    except SQLParseError as exc:
        return SQLValidationResult(
            is_valid=False,
            sql=sql,
            normalized_sql=sql,
            violations=[str(exc)],
        )

    violations: list[str] = []
    if not isinstance(expression, ALLOWED_QUERY_ROOT_TYPES):
        violations.append("Only SELECT query forms are allowed.")

    forbidden_types = {
        expr.key.upper()
        for forbidden_type in FORBIDDEN_STATEMENT_TYPES
        for expr in expression.find_all(forbidden_type)
    }
    if forbidden_types:
        violations.append(
            "Forbidden SQL statement(s) detected: "
            + ", ".join(sorted(forbidden_types))
        )

    if not any(True for _ in expression.find_all(exp.Select)):
        violations.append("SQL must contain a SELECT statement.")

    cte_names = _cte_names(expression)
    table_aliases: dict[str, str] = {}
    tables_used: list[str] = []

    for table in expression.find_all(exp.Table):
        if table.name in cte_names and not table.db:
            continue

        table_fqn, error = _resolve_table_fqn(
            table,
            snapshot,
            default_schema=default_schema,
        )
        if error:
            violations.append(error)
            continue
        assert table_fqn is not None
        if table_fqn not in tables_used:
            tables_used.append(table_fqn)

        alias = table.alias_or_name
        if alias:
            table_aliases[alias] = table_fqn

    allowed_table_set = set(allowed_tables or [])
    if allowed_table_set:
        for table_fqn in tables_used:
            if table_fqn not in allowed_table_set:
                violations.append(
                    f"Table '{table_fqn}' is outside the allowed retrieval scope."
                )

    columns_used: list[str] = []
    for column in expression.find_all(exp.Column):
        column_name = column.name
        if not column_name:
            continue

        column_table = column.table
        if column_table:
            if column_table in cte_names:
                continue
            resolved = table_aliases.get(column_table)
            if not resolved:
                violations.append(
                    f"Column '{column_table}.{column_name}' uses unknown table alias."
                )
                continue
            schema_name, table_name = resolved.split(".", 1)
            table_info = snapshot.schemas[schema_name].tables[table_name]
            if column_name not in table_info.columns:
                violations.append(
                    f"Column '{column_table}.{column_name}' is not present in '{resolved}'."
                )
                continue
            columns_used.append(f"{resolved}.{column_name}")
            continue

        matches: list[str] = []
        for table_fqn in tables_used:
            schema_name, table_name = table_fqn.split(".", 1)
            table_info = snapshot.schemas[schema_name].tables[table_name]
            if column_name in table_info.columns:
                matches.append(table_fqn)

        if not matches:
            violations.append(
                f"Unqualified column '{column_name}' is not present in selected tables."
            )
        elif len(matches) > 1:
            violations.append(
                f"Unqualified column '{column_name}' is ambiguous across: "
                + ", ".join(sorted(matches))
            )
        else:
            columns_used.append(f"{matches[0]}.{column_name}")

    if any(True for _ in expression.find_all(exp.Star)):
        violations.append("SELECT * is not allowed; select explicit columns.")

    limit_added = False
    if enforce_limit and not violations and _non_aggregate_query(expression):
        limit_capable_types = (exp.Select, exp.Union, exp.Intersect, exp.Except)
        if isinstance(expression, limit_capable_types) and expression.args.get(
            "limit"
        ) is None:
            expression = expression.limit(default_limit)
            limit_added = True

    normalized_sql = expression.sql(dialect="postgres", pretty=True)
    return SQLValidationResult(
        is_valid=not violations,
        sql=sql,
        normalized_sql=normalized_sql,
        tables_used=sorted(set(tables_used)),
        columns_used=sorted(set(columns_used)),
        violations=violations,
        limit_added=limit_added,
    )


def ensure_valid_sql(
    sql: str,
    snapshot: SchemaSnapshot,
    *,
    allowed_tables: list[str] | None = None,
    default_schema: str = "public",
    enforce_limit: bool = True,
    default_limit: int = DEFAULT_NON_AGGREGATE_LIMIT,
) -> SQLValidationResult:
    """Validate SQL and raise when violations are present."""
    result = validate_sql(
        sql,
        snapshot,
        allowed_tables=allowed_tables,
        default_schema=default_schema,
        enforce_limit=enforce_limit,
        default_limit=default_limit,
    )
    if not result.is_valid:
        raise SQLValidationError("\n".join(f"- {item}" for item in result.violations))
    return result
