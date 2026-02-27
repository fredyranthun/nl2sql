"""PostgreSQL connection and health check utilities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import psycopg


class DatabaseConnectionError(RuntimeError):
    """Raised when a PostgreSQL connection or health check fails."""


@dataclass(frozen=True)
class HealthcheckResult:
    """Information returned by a successful PostgreSQL health check."""

    current_database: str
    current_user: str
    server_version: str
    transaction_read_only: bool


@contextmanager
def connect_readonly(postgres_dsn: str) -> Iterator[psycopg.Connection]:
    """Open a PostgreSQL connection configured as read-only by default."""
    try:
        with psycopg.connect(
            postgres_dsn,
            connect_timeout=5,
            options="-c default_transaction_read_only=on",
        ) as conn:
            yield conn
    except psycopg.Error as exc:
        raise DatabaseConnectionError(
            f"Could not connect to PostgreSQL with provided DSN: {exc}"
        ) from exc


def check_postgres_health(postgres_dsn: str) -> HealthcheckResult:
    """Run a lightweight database health check and verify read-only mode."""
    try:
        with connect_readonly(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      current_database(),
                      current_user,
                      current_setting('server_version'),
                      current_setting('transaction_read_only')
                    """
                )
                row = cur.fetchone()
    except DatabaseConnectionError:
        raise
    except psycopg.Error as exc:
        raise DatabaseConnectionError(f"PostgreSQL health check failed: {exc}") from exc

    if row is None:
        raise DatabaseConnectionError("PostgreSQL health check returned no data.")

    current_database, current_user, server_version, read_only = row
    transaction_read_only = read_only == "on"
    if not transaction_read_only:
        raise DatabaseConnectionError(
            "Connected successfully but session is not read-only."
        )

    return HealthcheckResult(
        current_database=current_database,
        current_user=current_user,
        server_version=server_version,
        transaction_read_only=transaction_read_only,
    )
