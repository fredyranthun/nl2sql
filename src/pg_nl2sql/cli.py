"""Command-line entrypoint for pg-nl2sql."""

from __future__ import annotations

import argparse
import json
import sys

from pg_nl2sql import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pg-nl2sql",
        description=(
            "Safe PostgreSQL-focused CLI that turns natural language into "
            "SQL for human review."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "config-check",
        help="Validate environment configuration for pg-nl2sql.",
    )
    subparsers.add_parser(
        "healthcheck",
        help="Check PostgreSQL connectivity with a read-only session.",
    )
    introspect_parser = subparsers.add_parser(
        "introspect-schema",
        help="Inspect PostgreSQL schema metadata (Step 4).",
    )
    introspect_parser.add_argument(
        "--schema",
        action="append",
        default=None,
        help="Schema(s) to introspect. Repeat the flag to include multiple schemas.",
    )
    refresh_parser = subparsers.add_parser(
        "refresh-schema",
        help="Refresh local schema cache from PostgreSQL introspection.",
    )
    refresh_parser.add_argument(
        "--schema",
        action="append",
        default=None,
        help="Schema(s) to include in cache refresh. Repeat for multiple schemas.",
    )
    subparsers.add_parser(
        "show-cache",
        help="Show metadata from the local schema cache file.",
    )
    retrieve_parser = subparsers.add_parser(
        "retrieve-tables",
        help="Select relevant tables from schema cache for a NL question.",
    )
    retrieve_parser.add_argument("question", help="Natural language question.")
    retrieve_parser.add_argument(
        "--top-k",
        type=int,
        default=6,
        help="Maximum number of tables to return (default: 6).",
    )
    prompt_parser = subparsers.add_parser(
        "build-prompt",
        help="Build deterministic SQL-generation prompt from schema cache.",
    )
    prompt_parser.add_argument("question", help="Natural language question.")
    prompt_parser.add_argument(
        "--top-k",
        type=int,
        default=6,
        help="Maximum number of relevant tables to include (default: 6).",
    )
    generate_parser = subparsers.add_parser(
        "generate-sql",
        help="Generate structured SQL payload using configured LLM adapter.",
    )
    generate_parser.add_argument("question", help="Natural language question.")
    generate_parser.add_argument(
        "--top-k",
        type=int,
        default=6,
        help="Maximum number of relevant tables to include (default: 6).",
    )
    validate_parser = subparsers.add_parser(
        "validate-sql",
        help="Validate a SQL statement against safety and schema allowlist rules.",
    )
    validate_parser.add_argument("sql", help="SQL statement to validate.")
    validate_parser.add_argument(
        "--allow-table",
        action="append",
        default=None,
        help=(
            "Restrict SQL usage to fully-qualified table(s), "
            "for example --allow-table public.orders."
        ),
    )
    subparsers.add_parser("repl", help="Reserved for Step 10.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        print(
            "\nBootstrap status: Step 1 complete. "
            "Runtime commands will be implemented in upcoming steps."
        )
        return 0

    if args.command == "config-check":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
        except ModuleNotFoundError:
            print(
                "Configuration tooling dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2

        redacted = "***" if settings.openai_api_key else "(not set)"
        print("Configuration loaded successfully:")
        print(f"- POSTGRES_DSN: {settings.postgres_dsn}")
        print(f"- OPENAI_API_KEY: {redacted}")
        print(f"- OPENAI_MODEL: {settings.openai_model}")
        print(f"- SCHEMA_CACHE_PATH: {settings.schema_cache_path}")
        print(f"- DEFAULT_SCHEMA: {settings.default_schema}")
        return 0

    if args.command == "healthcheck":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.db.connection import (
                DatabaseConnectionError,
                check_postgres_health,
            )
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            result = check_postgres_health(settings.postgres_dsn)
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except DatabaseConnectionError as exc:
            print(f"Healthcheck failed:\n{exc}", file=sys.stderr)
            return 1

        print("PostgreSQL healthcheck succeeded:")
        print(f"- database: {result.current_database}")
        print(f"- user: {result.current_user}")
        print(f"- server_version: {result.server_version}")
        print(f"- transaction_read_only: {result.transaction_read_only}")
        return 0

    if args.command == "introspect-schema":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.db.introspect import IntrospectionError, introspect_schema
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            snapshot = introspect_schema(
                postgres_dsn=settings.postgres_dsn,
                default_schema=settings.default_schema,
                include_schemas=args.schema,
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except IntrospectionError as exc:
            print(f"Schema introspection failed:\n{exc}", file=sys.stderr)
            return 1

        print("Schema introspection succeeded:")
        print(f"- database: {snapshot.database}")
        print(f"- schemas: {', '.join(sorted(snapshot.schemas.keys())) or '(none)'}")
        print(f"- tables_and_views: {snapshot.table_count}")
        return 0

    if args.command == "refresh-schema":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.schema.cache import CacheError, refresh_schema_cache
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            cached = refresh_schema_cache(
                postgres_dsn=settings.postgres_dsn,
                cache_path=settings.schema_cache_path,
                default_schema=settings.default_schema,
                include_schemas=args.schema,
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache refresh failed:\n{exc}", file=sys.stderr)
            return 1

        print("Schema cache refresh succeeded:")
        print(f"- cache_path: {settings.schema_cache_path}")
        print(f"- cache_format_version: {cached.cache_format_version}")
        print(f"- generated_at: {cached.generated_at}")
        print(f"- database: {cached.snapshot.database}")
        print(
            f"- schemas: {', '.join(sorted(cached.snapshot.schemas.keys())) or '(none)'}"
        )
        print(f"- tables_and_views: {cached.snapshot.table_count}")
        return 0

    if args.command == "show-cache":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.schema.cache import CacheError, load_schema_cache
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            cached = load_schema_cache(settings.schema_cache_path)
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache read failed:\n{exc}", file=sys.stderr)
            return 1

        print("Schema cache loaded:")
        print(f"- cache_path: {settings.schema_cache_path}")
        print(f"- cache_format_version: {cached.cache_format_version}")
        print(f"- generated_at: {cached.generated_at}")
        print(f"- database: {cached.snapshot.database}")
        print(
            f"- schemas: {', '.join(sorted(cached.snapshot.schemas.keys())) or '(none)'}"
        )
        print(f"- tables_and_views: {cached.snapshot.table_count}")
        return 0

    if args.command == "retrieve-tables":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.schema.cache import CacheError, load_schema_cache
            from pg_nl2sql.schema.retrieval import (
                RetrievalError,
                retrieve_relevant_tables,
            )
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            cached = load_schema_cache(settings.schema_cache_path)
            result = retrieve_relevant_tables(
                args.question, cached.snapshot, top_k=args.top_k
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache read failed:\n{exc}", file=sys.stderr)
            return 1
        except RetrievalError as exc:
            print(f"Table retrieval failed:\n{exc}", file=sys.stderr)
            return 1

        print("Retrieved tables:")
        if not result.selected_tables:
            print("- (none)")
            return 0

        for item in result.selected_tables:
            marker = " [fk-expanded]" if item.expanded_by_fk else ""
            print(f"- {item.fqn} score={item.score:.3f}{marker}")
            print(f"  reasons: {', '.join(item.reasons)}")
        return 0

    if args.command == "build-prompt":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.prompts.sql_generation import (
                PromptBuildError,
                build_sql_generation_prompt,
            )
            from pg_nl2sql.schema.cache import CacheError, load_schema_cache
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            cached = load_schema_cache(settings.schema_cache_path)
            bundle = build_sql_generation_prompt(
                args.question,
                cached.snapshot,
                top_k=args.top_k,
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache read failed:\n{exc}", file=sys.stderr)
            return 1
        except PromptBuildError as exc:
            print(f"Prompt build failed:\n{exc}", file=sys.stderr)
            return 1

        print("Prompt build succeeded:")
        print(f"- question: {bundle.question}")
        print(
            "- retrieved_tables: "
            f"{', '.join(bundle.retrieved_tables) if bundle.retrieved_tables else '(none)'}"
        )
        print("\n--- SYSTEM PROMPT ---")
        print(bundle.system_prompt)
        print("\n--- USER PROMPT ---")
        print(bundle.user_prompt)
        return 0

    if args.command == "generate-sql":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.llm import LLMError, create_llm_generator
            from pg_nl2sql.prompts.sql_generation import (
                PromptBuildError,
                build_sql_generation_prompt,
            )
            from pg_nl2sql.schema.cache import CacheError, load_schema_cache
            from pg_nl2sql.sql.validator import SQLValidationError, ensure_valid_sql
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            settings.validate_llm_requirements()
            cached = load_schema_cache(settings.schema_cache_path)
            prompt_bundle = build_sql_generation_prompt(
                args.question,
                cached.snapshot,
                top_k=args.top_k,
            )
            llm = create_llm_generator(settings)
            result = llm.generate_sql(prompt_bundle)
            validation = ensure_valid_sql(
                result.sql,
                cached.snapshot,
                allowed_tables=prompt_bundle.retrieved_tables,
                default_schema=settings.default_schema,
            )
            result.sql = validation.normalized_sql
            if not result.tables_used:
                result.tables_used = validation.tables_used
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache read failed:\n{exc}", file=sys.stderr)
            return 1
        except PromptBuildError as exc:
            print(f"Prompt build failed:\n{exc}", file=sys.stderr)
            return 1
        except LLMError as exc:
            print(f"SQL generation failed:\n{exc}", file=sys.stderr)
            return 1
        except SQLValidationError as exc:
            print(f"Generated SQL failed validation:\n{exc}", file=sys.stderr)
            return 1

        print("SQL generation succeeded:")
        print(f"- confidence: {result.confidence:.3f}")
        print(
            "- tables_used: "
            f"{', '.join(result.tables_used) if result.tables_used else '(none)'}"
        )
        print("- assumptions:")
        if result.assumptions:
            for assumption in result.assumptions:
                print(f"  - {assumption}")
        else:
            print("  - (none)")
        print("\nSQL:")
        print(result.sql)
        print("\nJSON payload:")
        print(json.dumps(result.model_dump(), indent=2, sort_keys=True))
        return 0

    if args.command == "validate-sql":
        try:
            from pg_nl2sql.config import ConfigError, load_settings
            from pg_nl2sql.schema.cache import CacheError, load_schema_cache
            from pg_nl2sql.sql.validator import validate_sql
        except ModuleNotFoundError:
            print(
                "Runtime dependencies are missing. "
                "Install project dependencies first (pip install -e .).",
                file=sys.stderr,
            )
            return 2

        try:
            settings = load_settings()
            cached = load_schema_cache(settings.schema_cache_path)
            validation = validate_sql(
                args.sql,
                cached.snapshot,
                allowed_tables=args.allow_table,
                default_schema=settings.default_schema,
            )
        except ConfigError as exc:
            print(f"Configuration error:\n{exc}", file=sys.stderr)
            return 2
        except CacheError as exc:
            print(f"Schema cache read failed:\n{exc}", file=sys.stderr)
            return 1

        if not validation.is_valid:
            print("SQL validation failed:")
            for violation in validation.violations:
                print(f"- {violation}")
            return 1

        print("SQL validation succeeded:")
        print(
            "- tables_used: "
            f"{', '.join(validation.tables_used) if validation.tables_used else '(none)'}"
        )
        print(
            "- columns_used: "
            f"{', '.join(validation.columns_used) if validation.columns_used else '(none)'}"
        )
        print(f"- limit_added: {'yes' if validation.limit_added else 'no'}")
        print("\nNormalized SQL:")
        print(validation.normalized_sql)
        return 0

    print(f"Command '{args.command}' is not implemented yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
