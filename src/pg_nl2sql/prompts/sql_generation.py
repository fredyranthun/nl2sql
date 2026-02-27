"""Prompt builder for deterministic NL-to-SQL generation requests."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pg_nl2sql.db.introspect import SchemaSnapshot
from pg_nl2sql.schema.retrieval import (
    RetrievalError,
    RetrievalResult,
    retrieve_relevant_tables,
)


class PromptBuildError(RuntimeError):
    """Raised when SQL generation prompt building cannot proceed safely."""


@dataclass(frozen=True)
class PromptBundle:
    """Inspectable prompt bundle used by the LLM adapter."""

    question: str
    retrieved_tables: list[str]
    schema_subset_json: str
    output_contract_json: str
    system_prompt: str
    user_prompt: str


_OUTPUT_CONTRACT = {
    "type": "object",
    "required": ["sql", "assumptions", "tables_used", "confidence"],
    "properties": {
        "sql": {
            "type": "string",
            "description": "A single PostgreSQL SELECT query. No markdown.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short assumptions used to map NL to schema.",
        },
        "tables_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Fully-qualified tables referenced by the SQL.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Estimated confidence in the SQL interpretation.",
        },
    },
}


def _schema_subset_dict(
    snapshot: SchemaSnapshot,
    retrieval_result: RetrievalResult,
) -> dict[str, object]:
    schemas: dict[str, dict[str, object]] = {}

    for fqn in sorted(retrieval_result.tables_used):
        try:
            schema_name, table_name = fqn.split(".", 1)
        except ValueError as exc:
            raise PromptBuildError(f"Invalid retrieved table identifier: {fqn!r}") from exc

        schema = snapshot.schemas.get(schema_name)
        if not schema or table_name not in schema.tables:
            raise PromptBuildError(
                "Retrieved table is not present in schema snapshot: "
                f"{schema_name}.{table_name}"
            )

        table = schema.tables[table_name]
        schema_entry = schemas.setdefault(schema_name, {"tables": {}})
        tables_entry = schema_entry["tables"]
        assert isinstance(tables_entry, dict)
        tables_entry[table_name] = {
            "type": table.table_type,
            "description": table.description,
            "columns": {
                column_name: {
                    "type": table.columns[column_name].data_type,
                    "nullable": table.columns[column_name].nullable,
                    "description": table.columns[column_name].description,
                }
                for column_name in sorted(table.columns.keys())
            },
            "primary_key": sorted(table.primary_key),
            "foreign_keys": [
                {
                    "name": fk.name,
                    "columns": list(fk.columns),
                    "references": {
                        "schema": fk.references.schema,
                        "table": fk.references.table,
                        "columns": list(fk.references.columns),
                    },
                }
                for fk in sorted(table.foreign_keys, key=lambda item: item.name)
            ],
        }

    return {
        "database": snapshot.database,
        "schemas": schemas,
    }


def build_sql_generation_prompt(
    question: str,
    snapshot: SchemaSnapshot,
    *,
    retrieval_result: RetrievalResult | None = None,
    top_k: int = 6,
) -> PromptBundle:
    """Build deterministic prompts constrained to the relevant schema subset."""
    normalized_question = question.strip()
    if not normalized_question:
        raise PromptBuildError("Question cannot be empty.")

    try:
        retrieval = retrieval_result or retrieve_relevant_tables(
            normalized_question,
            snapshot,
            top_k=top_k,
        )
    except RetrievalError as exc:
        raise PromptBuildError(str(exc)) from exc

    if not retrieval.selected_tables:
        raise PromptBuildError("No relevant tables were selected for prompt generation.")

    schema_subset = _schema_subset_dict(snapshot, retrieval)
    schema_subset_json = json.dumps(schema_subset, indent=2, sort_keys=True)
    output_contract_json = json.dumps(_OUTPUT_CONTRACT, indent=2, sort_keys=True)

    system_prompt = (
        "You are a PostgreSQL SQL generation assistant. "
        "Output JSON only and follow the response contract exactly. "
        "Generate one safe SELECT query for human review."
    )

    user_prompt = (
        "Task: Convert the natural language question into a PostgreSQL SELECT query.\n"
        "Constraints:\n"
        "- Use only tables and columns from the provided schema subset.\n"
        "- SELECT-only. Do not emit INSERT/UPDATE/DELETE/DDL.\n"
        "- Prefer explicit column lists and table aliases.\n"
        "- Avoid SELECT *.\n"
        "- Add LIMIT 100 for non-aggregate queries when no natural bound exists.\n\n"
        f"Question:\n{normalized_question}\n\n"
        f"Relevant tables:\n{json.dumps(sorted(retrieval.tables_used), indent=2)}\n\n"
        f"Schema subset:\n{schema_subset_json}\n\n"
        f"Response contract (JSON Schema-like):\n{output_contract_json}\n\n"
        "Return only a JSON object matching the contract."
    )

    return PromptBundle(
        question=normalized_question,
        retrieved_tables=sorted(retrieval.tables_used),
        schema_subset_json=schema_subset_json,
        output_contract_json=output_contract_json,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
