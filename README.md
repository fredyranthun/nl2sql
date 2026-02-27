# pg-nl2sql

A safe PostgreSQL-focused CLI that converts natural language into SQL for human review.

## MVP Features
- Read-only PostgreSQL introspection
- Local schema cache
- Natural language to SQL generation
- SQL guardrails and validation
- Interactive REPL

## MVP Non-Goals
- Automatic SQL execution
- GUI or web application
- Multi-database support

## Requirements
- Python 3.12+

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## CLI Usage
```bash
python -m pg_nl2sql.cli --help
pg-nl2sql --help
pg-nl2sql --version
pg-nl2sql config-check
pg-nl2sql healthcheck
pg-nl2sql introspect-schema
pg-nl2sql refresh-schema
pg-nl2sql show-cache
pg-nl2sql retrieve-tables "orders by status in the last 7 days"
pg-nl2sql build-prompt "orders by status in the last 7 days"
```

## Current Status
- Step 1 (Bootstrap repository): complete
- Step 2 (Configuration layer): complete
- Step 3 (PostgreSQL connection + healthcheck): complete
- Step 4 (Schema introspection): complete
- Step 5 (Local schema cache): complete
- Step 6 (Retrieval heuristics): complete
- Step 7 (Prompt builder): complete
- Steps 8-11: planned

## Planned Architecture
```text
User Question (NL)
   -> REPL
   -> Retriever (relevant schema objects)
   -> Prompt Builder
   -> LLM SQL Generator
   -> SQL Validator / Guardrails
   -> Structured Output
      - sql
      - assumptions
      - tables_used
      - confidence
```

## Development Roadmap
1. LLM adapter
2. SQL validator
3. REPL
4. Tests
