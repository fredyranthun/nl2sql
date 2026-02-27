"""Heuristic schema retrieval for NL-to-SQL prompt narrowing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pg_nl2sql.db.introspect import SchemaSnapshot, TableInfo

_TOKEN_SPLIT = re.compile(r"[^a-z0-9_]+")


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot proceed safely."""


@dataclass(frozen=True)
class RetrievedTable:
    """Single retrieved table with score and match details."""

    schema: str
    table: str
    score: float
    reasons: list[str]
    expanded_by_fk: bool = False

    @property
    def fqn(self) -> str:
        return f"{self.schema}.{self.table}"


@dataclass(frozen=True)
class RetrievalResult:
    """Ranked retrieval result for a natural language question."""

    question: str
    selected_tables: list[RetrievedTable] = field(default_factory=list)

    @property
    def tables_used(self) -> list[str]:
        return [item.fqn for item in self.selected_tables]


def _tokenize(value: str) -> set[str]:
    cleaned = value.lower().strip()
    if not cleaned:
        return set()
    return {token for token in _TOKEN_SPLIT.split(cleaned) if token}


def _table_tokens(table: TableInfo, schema_name: str) -> set[str]:
    tokens = _tokenize(table.name) | _tokenize(schema_name)
    for column_name, column in table.columns.items():
        tokens |= _tokenize(column_name)
        if column.description:
            tokens |= _tokenize(column.description)
    if table.description:
        tokens |= _tokenize(table.description)
    return tokens


def _fk_adjacency(snapshot: SchemaSnapshot) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for schema_name, schema in snapshot.schemas.items():
        for table_name, table in schema.tables.items():
            src = f"{schema_name}.{table_name}"
            graph.setdefault(src, set())
            for fk in table.foreign_keys:
                dst = f"{fk.references.schema}.{fk.references.table}"
                graph[src].add(dst)
                graph.setdefault(dst, set()).add(src)
    return graph


def retrieve_relevant_tables(
    question: str,
    snapshot: SchemaSnapshot,
    *,
    top_k: int = 6,
    min_score: float = 1.0,
    fk_expand: bool = True,
) -> RetrievalResult:
    """Rank relevant tables using lexical overlap and optional 1-hop FK expansion."""
    if not question.strip():
        raise RetrievalError("Question cannot be empty.")
    if top_k < 1:
        raise RetrievalError("top_k must be >= 1.")

    question_tokens = _tokenize(question)
    if not question_tokens:
        raise RetrievalError("Question does not contain searchable tokens.")

    candidate_scores: dict[str, tuple[float, list[str]]] = {}
    table_lookup: dict[str, tuple[str, TableInfo]] = {}

    for schema_name, schema in snapshot.schemas.items():
        for table_name, table in schema.tables.items():
            fqn = f"{schema_name}.{table_name}"
            table_lookup[fqn] = (schema_name, table)
            reasons: list[str] = []
            score = 0.0

            table_name_tokens = _tokenize(table_name)
            schema_tokens = _tokenize(schema_name)
            description_tokens = _tokenize(table.description or "")
            column_name_tokens: set[str] = set()
            column_desc_tokens: set[str] = set()
            for column_name, column in table.columns.items():
                column_name_tokens |= _tokenize(column_name)
                column_desc_tokens |= _tokenize(column.description or "")

            exact_table_hits = question_tokens & table_name_tokens
            exact_schema_hits = question_tokens & schema_tokens
            column_name_hits = question_tokens & column_name_tokens
            description_hits = question_tokens & description_tokens
            column_desc_hits = question_tokens & column_desc_tokens

            if exact_table_hits:
                score += 4.0 + 0.5 * len(exact_table_hits)
                reasons.append(f"table_name_match={','.join(sorted(exact_table_hits))}")
            if exact_schema_hits:
                score += 1.5 + 0.25 * len(exact_schema_hits)
                reasons.append(f"schema_match={','.join(sorted(exact_schema_hits))}")
            if column_name_hits:
                score += 2.5 + 0.2 * len(column_name_hits)
                reasons.append(f"column_match={','.join(sorted(column_name_hits))}")
            if description_hits:
                score += 1.0 + 0.1 * len(description_hits)
                reasons.append(f"table_description_match={','.join(sorted(description_hits))}")
            if column_desc_hits:
                score += 0.8 + 0.1 * len(column_desc_hits)
                reasons.append(
                    f"column_description_match={','.join(sorted(column_desc_hits))}"
                )

            # Small coverage bonus for broad overlap across all table text.
            overlap_count = len(question_tokens & _table_tokens(table, schema_name))
            if overlap_count:
                score += min(1.5, overlap_count * 0.15)

            if score >= min_score:
                candidate_scores[fqn] = (score, reasons)

    ranked_base = sorted(
        candidate_scores.items(),
        key=lambda item: (-item[1][0], item[0]),
    )

    selected: list[RetrievedTable] = []
    seen: set[str] = set()

    for fqn, (score, reasons) in ranked_base[:top_k]:
        schema_name, table = table_lookup[fqn]
        selected.append(
            RetrievedTable(
                schema=schema_name,
                table=table.name,
                score=round(score, 3),
                reasons=reasons,
                expanded_by_fk=False,
            )
        )
        seen.add(fqn)

    if fk_expand and selected:
        graph = _fk_adjacency(snapshot)
        for base in list(selected):
            if len(selected) >= top_k:
                break
            for neighbor in sorted(graph.get(base.fqn, set())):
                if neighbor in seen or neighbor not in table_lookup:
                    continue
                schema_name, table = table_lookup[neighbor]
                selected.append(
                    RetrievedTable(
                        schema=schema_name,
                        table=table.name,
                        score=round(max(0.5, base.score - 1.0), 3),
                        reasons=[f"fk_neighbor_of={base.fqn}"],
                        expanded_by_fk=True,
                    )
                )
                seen.add(neighbor)
                if len(selected) >= top_k:
                    break

    selected_sorted = sorted(
        selected,
        key=lambda item: (-item.score, item.fqn),
    )[:top_k]
    return RetrievalResult(question=question, selected_tables=selected_sorted)
