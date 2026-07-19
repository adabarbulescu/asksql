from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from asksql.models import (
    CancellationToken,
    Column,
    DatabaseObject,
    ForeignKey,
    IndexSchema,
    MutationResult,
    QueryCancelledError,
    QueryResult,
    QueryTimeoutError,
    SchemaDetails,
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


def read_write_uri(db_url: str) -> str:
    return f"file:{db_path(db_url).resolve().as_posix()}?mode=rw"


def schema(db_url: str, table_names: list[str] | None = None) -> str:
    lines = []
    for table in inspect(db_url).values():
        if table_names is not None and table.name not in table_names:
            continue
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


def inspect_details(db_url: str) -> SchemaDetails:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        base = inspect(db_url)
        tables: dict[str, TableSchema] = {}
        for name, table in base.items():
            indexes = []
            for index_row in conn.execute(f"pragma index_list({quote_identifier(name)})").fetchall():
                index_name = str(index_row[1])
                columns = [
                    str(row[2])
                    for row in conn.execute(f"pragma index_info({quote_identifier(index_name)})").fetchall()
                    if row[2] is not None
                ]
                indexes.append(IndexSchema(index_name, columns, bool(index_row[2])))
            row_count = int(conn.execute(f"select count(*) from {quote_identifier(name)}").fetchone()[0])
            tables[name] = TableSchema(name, table.columns, table.foreign_keys, indexes, row_count)
        objects = conn.execute(
            """
            select name, type, tbl_name, sql from sqlite_master
            where type in ('view', 'trigger') and name not like 'sqlite_%'
            order by type, name
            """
        ).fetchall()
    views = [DatabaseObject(row[0], row[1], row[2], row[3]) for row in objects if row[1] == "view"]
    triggers = [DatabaseObject(row[0], row[1], row[2], row[3]) for row in objects if row[1] == "trigger"]
    return SchemaDetails(tables, views, triggers)


def explain_query_plan(db_url: str, sql: str) -> list[tuple[object, ...]]:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        return conn.execute(f"explain query plan {sql}").fetchall()


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


def execute_write(
    db_url: str,
    sql: str,
    timeout: float | None = DEFAULT_TIMEOUT,
    cancellation: CancellationToken | None = None,
) -> MutationResult:
    """Execute one write statement atomically against an existing SQLite database."""
    if cancellation and cancellation.cancelled:
        raise QueryCancelledError("query cancelled")
    deadline = time.monotonic() + timeout if timeout is not None else None
    interrupt_reason: str | None = None

    with sqlite3.connect(read_write_uri(db_url), uri=True) as conn:
        conn.execute("pragma foreign_keys = on")
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
            if cancellation and cancellation.cancelled:
                raise QueryCancelledError("query cancelled")
            return MutationResult(max(cursor.rowcount, 0), cursor.lastrowid)
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
