from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_LIMIT = 200
MAX_LIMIT = 10_000


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool


@dataclass(frozen=True)
class ForeignKey:
    column: str
    referenced_table: str
    referenced_column: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: list[Column]
    foreign_keys: list[ForeignKey]


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[object, ...]]
    truncated: bool
    limit: int


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
                [Column(col[1], col[2], bool(col[5])) for col in conn.execute(f"pragma table_info({quote_identifier(table)})").fetchall()],
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


def limited_query(db_url: str, sql: str, limit: int = DEFAULT_LIMIT) -> tuple[list[str], list[tuple[object, ...]], bool]:
    result = query_result(db_url, sql, limit)
    return result.columns, result.rows, result.truncated


def query_result(db_url: str, sql: str, limit: int = DEFAULT_LIMIT) -> QueryResult:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(limit + 1)
        return QueryResult([col[0] for col in cursor.description or []], rows[:limit], len(rows) > limit, limit)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def preview_table(db_url: str, table: str, limit: int = 50) -> tuple[list[str], list[tuple[object, ...]]]:
    return query(db_url, f"select * from {quote_identifier(table)} limit {limit}")
