"""Command-line entrypoint for pg-nl2sql."""

from __future__ import annotations

import argparse
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
    subparsers.add_parser("healthcheck", help="Reserved for Step 3.")
    subparsers.add_parser("refresh-schema", help="Reserved for Step 5.")
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
        except ModuleNotFoundError as exc:
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

    print(f"Command '{args.command}' is not implemented yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
