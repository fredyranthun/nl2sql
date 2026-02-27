"""PostgreSQL schema introspection with normalized output models."""

from __future__ import annotations

from dataclasses import dataclass, field

from pg_nl2sql.db.connection import DatabaseConnectionError, connect_readonly
from pg_nl2sql.db.queries import (
    COLUMNS_QUERY,
    FOREIGN_KEYS_QUERY,
    PRIMARY_KEYS_QUERY,
    TABLES_QUERY,
)


class IntrospectionError(RuntimeError):
    """Raised when schema introspection fails."""


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    description: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.data_type,
            "nullable": self.nullable,
            "description": self.description,
        }


@dataclass(frozen=True)
class ForeignKeyReference:
    schema: str
    table: str
    columns: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "table": self.table,
            "columns": self.columns,
        }


@dataclass(frozen=True)
class ForeignKeyInfo:
    name: str
    columns: list[str]
    references: ForeignKeyReference

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "columns": self.columns,
            "references": self.references.to_dict(),
        }


@dataclass
class TableInfo:
    schema: str
    name: str
    table_type: str
    description: str | None
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.table_type,
            "description": self.description,
            "columns": {
                column_name: column.to_dict()
                for column_name, column in self.columns.items()
            },
            "primary_key": self.primary_key,
            "foreign_keys": [fk.to_dict() for fk in self.foreign_keys],
        }


@dataclass
class SchemaInfo:
    name: str
    tables: dict[str, TableInfo] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "tables": {
                table_name: table.to_dict()
                for table_name, table in self.tables.items()
            }
        }


@dataclass
class SchemaSnapshot:
    database: str
    schemas: dict[str, SchemaInfo] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "database": self.database,
            "schemas": {
                schema_name: schema.to_dict()
                for schema_name, schema in self.schemas.items()
            },
        }

    @property
    def table_count(self) -> int:
        return sum(len(schema.tables) for schema in self.schemas.values())


def _default_target_schemas(default_schema: str) -> list[str]:
    system = {"pg_catalog", "information_schema"}
    targets = {default_schema.strip() or "public"}
    return sorted(targets - system)


def introspect_schema(
    postgres_dsn: str,
    default_schema: str = "public",
    include_schemas: list[str] | None = None,
) -> SchemaSnapshot:
    """Introspect PostgreSQL table/view metadata into normalized structures."""
    target_schemas = (
        sorted({schema.strip() for schema in include_schemas if schema.strip()})
        if include_schemas
        else _default_target_schemas(default_schema)
    )
    if not target_schemas:
        raise IntrospectionError("No target schemas selected for introspection.")

    try:
        with connect_readonly(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                db_row = cur.fetchone()
                if not db_row:
                    raise IntrospectionError(
                        "Could not determine current PostgreSQL database."
                    )
                snapshot = SchemaSnapshot(database=db_row[0], schemas={})

                cur.execute(TABLES_QUERY, {"schemas": target_schemas})
                table_rows = cur.fetchall()

                for schema_name, table_name, table_type, table_description in table_rows:
                    schema = snapshot.schemas.setdefault(
                        schema_name, SchemaInfo(name=schema_name)
                    )
                    schema.tables[table_name] = TableInfo(
                        schema=schema_name,
                        name=table_name,
                        table_type=table_type,
                        description=table_description,
                    )

                cur.execute(COLUMNS_QUERY, {"schemas": target_schemas})
                for (
                    schema_name,
                    table_name,
                    column_name,
                    data_type,
                    is_nullable,
                    _ordinal,
                    column_description,
                ) in cur.fetchall():
                    table = snapshot.schemas.get(schema_name, SchemaInfo(name=schema_name))
                    if schema_name not in snapshot.schemas:
                        snapshot.schemas[schema_name] = table
                    if table_name not in table.tables:
                        table.tables[table_name] = TableInfo(
                            schema=schema_name,
                            name=table_name,
                            table_type="BASE TABLE",
                            description=None,
                        )
                    table.tables[table_name].columns[column_name] = ColumnInfo(
                        name=column_name,
                        data_type=data_type,
                        nullable=is_nullable == "YES",
                        description=column_description,
                    )

                cur.execute(PRIMARY_KEYS_QUERY, {"schemas": target_schemas})
                for schema_name, table_name, column_name, _position in cur.fetchall():
                    table = snapshot.schemas[schema_name].tables.get(table_name)
                    if table:
                        table.primary_key.append(column_name)

                fk_index: dict[tuple[str, str, str], dict[str, object]] = {}
                cur.execute(FOREIGN_KEYS_QUERY, {"schemas": target_schemas})
                for (
                    schema_name,
                    table_name,
                    constraint_name,
                    _position,
                    column_name,
                    ref_table_schema,
                    ref_table_name,
                    ref_column_name,
                ) in cur.fetchall():
                    key = (schema_name, table_name, constraint_name)
                    entry = fk_index.setdefault(
                        key,
                        {
                            "columns": [],
                            "ref_columns": [],
                            "ref_schema": ref_table_schema,
                            "ref_table": ref_table_name,
                        },
                    )
                    entry["columns"].append(column_name)
                    entry["ref_columns"].append(ref_column_name)

                for (schema_name, table_name, constraint_name), entry in fk_index.items():
                    table = snapshot.schemas[schema_name].tables.get(table_name)
                    if table:
                        table.foreign_keys.append(
                            ForeignKeyInfo(
                                name=constraint_name,
                                columns=list(entry["columns"]),
                                references=ForeignKeyReference(
                                    schema=str(entry["ref_schema"]),
                                    table=str(entry["ref_table"]),
                                    columns=list(entry["ref_columns"]),
                                ),
                            )
                        )

                return snapshot
    except DatabaseConnectionError as exc:
        raise IntrospectionError(str(exc)) from exc
