from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from asksql.models import (
    CancellationToken,
    Column,
    ForeignKey,
    QueryCancelledError,
    QueryResult,
    QueryTimeoutError,
    TableSchema,
)

DEFAULT_LIMIT = 200
MAX_LIMIT = 10_000
DEFAULT_TIMEOUT = 30.0


def db_path(db_url: str) -> Path:
    parsed = urlparse(db_url)
    if parsed.scheme != "sqlite":
        raise ValueError("only sqlite:// URLs are supported")
    path = parsed.path if not parsed.netloc else f"{parsed.netloc}{parsed.path}"
    return Path(unquote(path)).expanduser()


def read_only_uri(db_url: str) -> str:
    return f"file:{db_path(db_url).resolve().as_posix()}?mode=ro"


def schema(db_url: str) -> str:
    lines = []
    for table in inspect(db_url).values():
        lines.append(f"{table.name}(")
        for column in table.columns:
            parts = [f"  {column.name} {column.type}".rstrip()]
            if column.primary_key:
                parts.append("PRIMARY KEY")
            if foreign_key := _foreign_key_for_column(table, column.name):
                parts.append(f"REFERENCES {foreign_key.referenced_table}({foreign_key.referenced_column})")
            lines.append(" ".join(parts) + ",")
        lines[-1] = lines[-1].rstrip(",")
        lines.append(")")
        lines.append("")
    return "\n".join(lines) or "(empty schema)"


def inspect(db_url: str) -> dict[str, TableSchema]:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        rows = conn.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name"
        ).fetchall()
        return {
            table: TableSchema(
                table,
                [
                    Column(col[1], col[2], bool(col[5]))
                    for col in conn.execute(f"pragma table_info({quote_identifier(table)})").fetchall()
                ],
                [
                    ForeignKey(row[3], row[2], row[4])
                    for row in conn.execute(f"pragma foreign_key_list({quote_identifier(table)})").fetchall()
                ],
            )
            for (table,) in rows
        }


def _foreign_key_for_column(table: TableSchema, column: str) -> ForeignKey | None:
    return next((foreign_key for foreign_key in table.foreign_keys if foreign_key.column == column), None)


def query(db_url: str, sql: str) -> tuple[list[str], list[tuple[object, ...]]]:
    columns, rows, _ = limited_query(db_url, sql)
    return columns, rows


def limited_query(
    db_url: str,
    sql: str,
    limit: int = DEFAULT_LIMIT,
    timeout: float | None = DEFAULT_TIMEOUT,
    cancellation: CancellationToken | None = None,
) -> tuple[list[str], list[tuple[object, ...]], bool]:
    result = query_result(db_url, sql, limit, timeout, cancellation)
    return result.columns, result.rows, result.truncated


def query_result(
    db_url: str,
    sql: str,
    limit: int = DEFAULT_LIMIT,
    timeout: float | None = DEFAULT_TIMEOUT,
    cancellation: CancellationToken | None = None,
) -> QueryResult:
    if cancellation and cancellation.cancelled:
        raise QueryCancelledError("query cancelled")
    deadline = time.monotonic() + timeout if timeout is not None else None
    interrupt_reason: str | None = None

    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        remove_interrupt = cancellation.add_callback(conn.interrupt) if cancellation else None

        def progress() -> int:
            nonlocal interrupt_reason
            if cancellation and cancellation.cancelled:
                interrupt_reason = "cancelled"
                return 1
            if deadline is not None and time.monotonic() >= deadline:
                interrupt_reason = "timeout"
                return 1
            return 0

        conn.set_progress_handler(progress, 1000)
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(limit + 1)
            return QueryResult([col[0] for col in cursor.description or []], rows[:limit], len(rows) > limit, limit)
        except sqlite3.OperationalError as exc:
            if cancellation and cancellation.cancelled:
                raise QueryCancelledError("query cancelled") from exc
            if deadline is not None and time.monotonic() >= deadline:
                raise QueryTimeoutError(f"query timed out after {timeout:g} seconds") from exc
            if interrupt_reason == "cancelled":
                raise QueryCancelledError("query cancelled") from exc
            if interrupt_reason == "timeout":
                raise QueryTimeoutError(f"query timed out after {timeout:g} seconds") from exc
            raise
        finally:
            conn.set_progress_handler(None, 0)
            if remove_interrupt:
                remove_interrupt()


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def preview_table(db_url: str, table: str, limit: int = 50) -> tuple[list[str], list[tuple[object, ...]]]:
    return query(db_url, f"select * from {quote_identifier(table)} limit {limit}")
