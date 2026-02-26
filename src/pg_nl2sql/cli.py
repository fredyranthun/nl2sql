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

    print(f"Command '{args.command}' is not implemented yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
