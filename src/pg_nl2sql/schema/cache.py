"""Schema cache persistence and refresh routines."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pg_nl2sql.db.introspect import (
    ColumnInfo,
    ForeignKeyInfo,
    ForeignKeyReference,
    IntrospectionError,
    SchemaInfo,
    SchemaSnapshot,
    TableInfo,
    introspect_schema,
)

CACHE_FORMAT_VERSION = "1.0"


class CacheError(RuntimeError):
    """Raised when schema cache operations fail."""


@dataclass(frozen=True)
class CachedSchemaSnapshot:
    """Versioned schema cache representation."""

    cache_format_version: str
    generated_at: str
    snapshot: SchemaSnapshot

    def to_dict(self) -> dict[str, object]:
        return {
            "cache_format_version": self.cache_format_version,
            "generated_at": self.generated_at,
            **self.snapshot.to_dict(),
        }


def _now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _parse_snapshot(payload: dict[str, Any]) -> SchemaSnapshot:
    database = payload.get("database")
    schemas_payload = payload.get("schemas")
    if not isinstance(database, str) or not database.strip():
        raise CacheError("Cached schema is missing a valid 'database' field.")
    if not isinstance(schemas_payload, dict):
        raise CacheError("Cached schema is missing a valid 'schemas' object.")

    schemas: dict[str, SchemaInfo] = {}
    for schema_name, schema_value in schemas_payload.items():
        if not isinstance(schema_value, dict):
            raise CacheError(f"Schema '{schema_name}' has invalid structure.")
        tables_payload = schema_value.get("tables", {})
        if not isinstance(tables_payload, dict):
            raise CacheError(f"Schema '{schema_name}' has invalid 'tables' structure.")

        schema_info = SchemaInfo(name=schema_name)
        for table_name, table_value in tables_payload.items():
            if not isinstance(table_value, dict):
                raise CacheError(f"Table '{schema_name}.{table_name}' is invalid.")

            columns_payload = table_value.get("columns", {})
            if not isinstance(columns_payload, dict):
                raise CacheError(
                    f"Table '{schema_name}.{table_name}' has invalid 'columns'."
                )
            columns: dict[str, ColumnInfo] = {}
            for column_name, column_value in columns_payload.items():
                if not isinstance(column_value, dict):
                    raise CacheError(
                        f"Column '{schema_name}.{table_name}.{column_name}' is invalid."
                    )
                column_type = column_value.get("type")
                nullable = column_value.get("nullable")
                description = column_value.get("description")
                if not isinstance(column_type, str):
                    raise CacheError(
                        f"Column '{schema_name}.{table_name}.{column_name}' missing type."
                    )
                if not isinstance(nullable, bool):
                    raise CacheError(
                        f"Column '{schema_name}.{table_name}.{column_name}' missing nullable."
                    )
                if description is not None and not isinstance(description, str):
                    raise CacheError(
                        f"Column '{schema_name}.{table_name}.{column_name}' has invalid description."
                    )
                columns[column_name] = ColumnInfo(
                    name=column_name,
                    data_type=column_type,
                    nullable=nullable,
                    description=description,
                )

            pk_payload = table_value.get("primary_key", [])
            if not isinstance(pk_payload, list) or not all(
                isinstance(item, str) for item in pk_payload
            ):
                raise CacheError(
                    f"Table '{schema_name}.{table_name}' has invalid primary_key."
                )

            fks_payload = table_value.get("foreign_keys", [])
            if not isinstance(fks_payload, list):
                raise CacheError(
                    f"Table '{schema_name}.{table_name}' has invalid foreign_keys."
                )

            foreign_keys: list[ForeignKeyInfo] = []
            for fk in fks_payload:
                if not isinstance(fk, dict):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' has invalid foreign key entry."
                    )
                fk_name = fk.get("name")
                fk_columns = fk.get("columns")
                references = fk.get("references")
                if not isinstance(fk_name, str):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' foreign key missing name."
                    )
                if not isinstance(fk_columns, list) or not all(
                    isinstance(item, str) for item in fk_columns
                ):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' foreign key '{fk_name}' has invalid columns."
                    )
                if not isinstance(references, dict):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' foreign key '{fk_name}' has invalid references."
                    )
                ref_schema = references.get("schema")
                ref_table = references.get("table")
                ref_columns = references.get("columns")
                if not isinstance(ref_schema, str) or not isinstance(ref_table, str):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' foreign key '{fk_name}' has invalid referenced table."
                    )
                if not isinstance(ref_columns, list) or not all(
                    isinstance(item, str) for item in ref_columns
                ):
                    raise CacheError(
                        f"Table '{schema_name}.{table_name}' foreign key '{fk_name}' has invalid referenced columns."
                    )
                foreign_keys.append(
                    ForeignKeyInfo(
                        name=fk_name,
                        columns=fk_columns,
                        references=ForeignKeyReference(
                            schema=ref_schema,
                            table=ref_table,
                            columns=ref_columns,
                        ),
                    )
                )

            table_info = TableInfo(
                schema=schema_name,
                name=table_name,
                table_type=str(table_value.get("type", "BASE TABLE")),
                description=table_value.get("description")
                if isinstance(table_value.get("description"), str)
                or table_value.get("description") is None
                else None,
                columns=columns,
                primary_key=pk_payload,
                foreign_keys=foreign_keys,
            )
            schema_info.tables[table_name] = table_info
        schemas[schema_name] = schema_info

    return SchemaSnapshot(database=database, schemas=schemas)


def save_schema_cache(cache_path: Path, snapshot: SchemaSnapshot) -> CachedSchemaSnapshot:
    """Persist schema snapshot to cache JSON with format metadata."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CacheError(f"Failed to create cache directory: {exc}") from exc

    cached = CachedSchemaSnapshot(
        cache_format_version=CACHE_FORMAT_VERSION,
        generated_at=_now_iso(),
        snapshot=snapshot,
    )
    try:
        cache_path.write_text(
            json.dumps(cached.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise CacheError(f"Failed to write schema cache file: {exc}") from exc
    return cached


def load_schema_cache(cache_path: Path) -> CachedSchemaSnapshot:
    """Load and validate cached schema JSON."""
    if not cache_path.exists():
        raise CacheError(f"Schema cache file does not exist: {cache_path}")

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CacheError(f"Schema cache file is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise CacheError(f"Failed to read schema cache file: {exc}") from exc

    if not isinstance(payload, dict):
        raise CacheError("Schema cache payload root must be a JSON object.")

    cache_format_version = payload.get("cache_format_version")
    if cache_format_version != CACHE_FORMAT_VERSION:
        raise CacheError(
            "Unsupported schema cache format version: "
            f"{cache_format_version!r}. Expected {CACHE_FORMAT_VERSION!r}."
        )

    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise CacheError("Schema cache is missing a valid 'generated_at' value.")

    snapshot = _parse_snapshot(payload)
    return CachedSchemaSnapshot(
        cache_format_version=cache_format_version,
        generated_at=generated_at,
        snapshot=snapshot,
    )


def refresh_schema_cache(
    postgres_dsn: str,
    cache_path: Path,
    default_schema: str = "public",
    include_schemas: list[str] | None = None,
) -> CachedSchemaSnapshot:
    """Introspect PostgreSQL schema and persist local cache."""
    try:
        snapshot = introspect_schema(
            postgres_dsn=postgres_dsn,
            default_schema=default_schema,
            include_schemas=include_schemas,
        )
    except IntrospectionError as exc:
        raise CacheError(str(exc)) from exc

    return save_schema_cache(cache_path=cache_path, snapshot=snapshot)
