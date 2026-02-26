# pg-nl2sql — Initial Project

## Goal

Build a local-first tool optimized for **PostgreSQL** that:

1. Connects to a database using a **read-only** user.
2. Introspects the schema safely.
3. Builds a local schema cache.
4. Exposes a **REPL** where the user writes a question in natural language.
5. Returns a **PostgreSQL SELECT query** for human review.
6. Does **not** execute SQL automatically in the MVP.

---

## Product scope for MVP

### Included

* PostgreSQL schema introspection
* Read-only connection
* Local schema cache in JSON
* Natural language to SQL generation
* SQL validation and safety checks
* Terminal REPL
* Assumptions/confidence/tables-used in output

### Excluded for MVP

* Automatic query execution
* Voice input
* GUI/web app
* Multi-database support
* Embeddings/vector search
* Autonomous agent behavior

---

## Technical decisions

### Language

* **Python 3.12+**

### Core libraries

* **psycopg** for PostgreSQL connectivity
* **sqlglot** for SQL parsing and validation
* **prompt_toolkit** for REPL UX
* **pydantic** for typed models/config
* **rich** for terminal formatting
* LLM provider adapter behind a simple interface

### Why this stack

* Fast MVP iteration
* Good ecosystem for text-to-SQL experiments
* Strong SQL parsing support
* Easy to keep architecture simple and auditable

---

## Architecture

```text
User Question (NL)
   -> REPL
   -> Retriever (select relevant schema objects)
   -> Prompt Builder
   -> LLM SQL Generator
   -> SQL Validator / Guardrails
   -> Structured Output
      - sql
      - assumptions
      - tables_used
      - confidence
```

---

## Proposed repository structure

```text
pg-nl2sql/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── Makefile
├── src/
│   └── pg_nl2sql/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── repl.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── schema.py
│       │   └── generation.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── introspect.py
│       │   └── queries.py
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── cache.py
│       │   ├── formatter.py
│       │   └── retrieval.py
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── openai_adapter.py
│       ├── sql/
│       │   ├── __init__.py
│       │   ├── parser.py
│       │   ├── validator.py
│       │   └── rules.py
│       └── prompts/
│           ├── __init__.py
│           └── sql_generation.py
├── tests/
│   ├── test_retrieval.py
│   ├── test_validator.py
│   └── test_prompt_builder.py
└── data/
    └── schema_cache.json
```

---

## Domain model

### Schema cache model

```json
{
  "database": "app_db",
  "schemas": {
    "public": {
      "tables": {
        "orders": {
          "description": "Customer orders",
          "columns": {
            "id": {
              "type": "uuid",
              "nullable": false,
              "description": "Primary key"
            },
            "customer_id": {
              "type": "uuid",
              "nullable": false,
              "description": "References customers"
            },
            "status": {
              "type": "text",
              "nullable": false,
              "description": "Current order status"
            },
            "created_at": {
              "type": "timestamp with time zone",
              "nullable": false,
              "description": "Creation timestamp"
            }
          },
          "primary_key": ["id"],
          "foreign_keys": [
            {
              "columns": ["customer_id"],
              "references": {
                "table": "customers",
                "columns": ["id"]
              }
            }
          ]
        }
      }
    }
  }
}
```

---

## Main modules

### `db/introspect.py`

Responsibilities:

* Connect using read-only credentials
* Read tables/views/columns/constraints
* Return normalized schema structures

### `schema/cache.py`

Responsibilities:

* Save/load schema cache JSON
* Refresh cache on demand
* Version the local cache format

### `schema/retrieval.py`

Responsibilities:

* Select relevant tables for a question
* Use heuristics first
* Expand related tables via FK graph

### `prompts/sql_generation.py`

Responsibilities:

* Build structured prompt for SQL generation
* Inject only the relevant schema subset
* Enforce output contract

### `llm/base.py`

Responsibilities:

* Define LLM interface
* Keep provider-independent generation layer

### `sql/validator.py`

Responsibilities:

* Parse generated SQL
* Ensure it is SELECT-only
* Block forbidden statements
* Check allowed tables/columns
* Enforce optional LIMIT rules

### `repl.py`

Responsibilities:

* Interactive terminal experience
* Commands like `/refresh-schema`, `/tables`, `/schema orders`
* Show SQL and metadata cleanly

---

## REPL UX

### User commands

* `/help`
* `/refresh-schema`
* `/tables`
* `/schema <table>`
* `/quit`

### Example session

```text
> pedidos criados nos ultimos 7 dias por status

Tables used: public.orders
Confidence: 0.84
Assumptions:
- "pedidos" refers to public.orders
- the relevant timestamp is orders.created_at

SQL:
SELECT
  o.status,
  COUNT(*) AS total_orders
FROM public.orders AS o
WHERE o.created_at >= NOW() - INTERVAL '7 days'
GROUP BY o.status
ORDER BY total_orders DESC;
```

---

## Guardrails

### Allowed

* `SELECT`
* joins between known tables
* aggregates
* CTEs only if SELECT-only

### Forbidden

* `INSERT`
* `UPDATE`
* `DELETE`
* `TRUNCATE`
* `DROP`
* `ALTER`
* `CREATE`
* access to tables outside schema cache allowlist

### Additional rules

* Prefer qualified columns with aliases
* Avoid `SELECT *`
* Add `LIMIT 100` to non-aggregate queries when natural limitation is absent

---

## Suggested configuration

### `.env.example`

```env
POSTGRES_DSN=postgresql://readonly_user:password@localhost:5432/app_db
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.2-mini
SCHEMA_CACHE_PATH=./data/schema_cache.json
DEFAULT_SCHEMA=public
```

---

## AGENTS.md

# AGENTS.md — pg-nl2sql

This file is the execution guide for a coding agent working on this repository.

## Mission

Build a safe MVP that converts natural language questions into PostgreSQL SELECT queries, based on a read-only schema introspection flow.

## Non-negotiable constraints

1. Never implement automatic SQL execution in MVP.
2. Only PostgreSQL support for now.
3. SQL output must be SELECT-only.
4. Keep architecture simple and explicit.
5. Prefer small steps with testable deliverables.
6. Avoid unnecessary frameworks and abstractions.

## Engineering principles

* Small commits
* Explicit types
* Clear module boundaries
* Fail closed on safety checks
* Log assumptions and reasoning metadata
* Keep prompts deterministic and auditable

## MVP execution steps

### Step 1 — Bootstrap repository

Deliver:

* `pyproject.toml`
* package structure under `src/pg_nl2sql`
* `README.md`
* `.env.example`
* minimal CLI entrypoint

Success criteria:

* project installs locally
* `python -m pg_nl2sql.cli --help` works

### Step 2 — Configuration layer

Deliver:

* typed config loader
* environment variable parsing
* validation for required settings

Success criteria:

* config loads from environment
* invalid config fails with friendly error

### Step 3 — PostgreSQL connection

Deliver:

* connection factory using `psycopg`
* health-check command

Success criteria:

* can open a connection with provided DSN
* connection errors are handled clearly

### Step 4 — Schema introspection

Deliver:

* introspection queries for tables, columns, PKs, FKs
* normalized in-memory schema objects

Success criteria:

* can introspect a real Postgres DB
* schema metadata is structured and consistent

### Step 5 — Schema cache

Deliver:

* save/load cache JSON
* refresh command

Success criteria:

* introspected schema can be persisted and loaded back
* `/refresh-schema` updates the cache file

### Step 6 — Retrieval heuristics

Deliver:

* select relevant tables by names/columns/descriptions
* 1-hop FK expansion

Success criteria:

* sample NL questions map to expected tables

### Step 7 — Prompt builder

Deliver:

* structured prompt using only relevant schema subset
* structured JSON output contract

Success criteria:

* prompt is deterministic and inspectable

### Step 8 — LLM adapter

Deliver:

* provider interface
* OpenAI adapter implementation

Success criteria:

* NL question returns structured generation payload

### Step 9 — SQL validation

Deliver:

* SQLGlot parser integration
* SELECT-only enforcement
* forbidden statement blocking
* allowlist validation

Success criteria:

* invalid SQL is rejected
* non-SELECT SQL is rejected

### Step 10 — REPL

Deliver:

* interactive prompt
* slash commands
* formatted output with SQL + assumptions + confidence

Success criteria:

* user can ask NL questions interactively
* tool returns generated SQL safely

### Step 11 — Tests

Deliver:

* validator tests
* retrieval tests
* prompt builder tests

Success criteria:

* core safety behavior is covered by tests

## Coding conventions

* Use `pathlib`
* Prefer dataclasses or pydantic models for structured data
* Use `rich` for terminal output
* Keep SQL introspection queries in dedicated files/modules
* Do not hardcode provider-specific logic outside `llm/`

## Commands

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Run CLI

```bash
python -m pg_nl2sql.cli --help
```

### Run tests

```bash
pytest
```

---

## Initial README outline

### README.md

```md
# pg-nl2sql

A safe PostgreSQL-focused CLI that converts natural language into SQL for review.

## MVP features
- Read-only PostgreSQL introspection
- Local schema cache
- Natural language to SQL generation
- SQL guardrails and validation
- Interactive REPL

## Status
Early MVP
```

---

## First implementation target

Start with these concrete files first:

* `pyproject.toml`
* `src/pg_nl2sql/cli.py`
* `src/pg_nl2sql/config.py`
* `src/pg_nl2sql/db/connection.py`
* `src/pg_nl2sql/db/introspect.py`
* `src/pg_nl2sql/schema/cache.py`
* `README.md`
* `.env.example`

---

## Recommended next turn

Generate the actual contents for:

1. `pyproject.toml`
2. `.env.example`
3. `README.md`
4. `src/pg_nl2sql/cli.py`
5. `src/pg_nl2sql/config.py`
