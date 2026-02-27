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
```

## Current Status
- Step 1 (Bootstrap repository): complete
- Step 2 (Configuration layer): complete
- Step 3 (PostgreSQL connection + healthcheck): complete
- Steps 4-11: planned

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
1. Schema introspection
2. Local schema cache
3. Retrieval heuristics
4. Prompt builder
5. LLM adapter
6. SQL validator
7. REPL
8. Tests
