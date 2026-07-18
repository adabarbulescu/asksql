from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


Column = tuple[str, str, bool]
DEFAULT_LIMIT = 200


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
    for table, columns in inspect(db_url).items():
        lines.append(f"{table}({', '.join(f'{name} {kind}'.strip() for name, kind, _ in columns)})")
    return "\n".join(lines) or "(empty schema)"


def inspect(db_url: str) -> dict[str, list[Column]]:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        rows = conn.execute(
            "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by name"
        ).fetchall()
        return {
            table: [(col[1], col[2], bool(col[5])) for col in conn.execute(f"pragma table_info({table!r})").fetchall()]
            for (table,) in rows
        }


def query(db_url: str, sql: str) -> tuple[list[str], list[tuple[object, ...]]]:
    result = query_result(db_url, sql)
    return result.columns, result.rows


def query_result(db_url: str, sql: str, limit: int = DEFAULT_LIMIT) -> QueryResult:
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(limit + 1)
        return QueryResult([col[0] for col in cursor.description or []], rows[:limit], len(rows) > limit, limit)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def preview_table(db_url: str, table: str, limit: int = 50) -> tuple[list[str], list[tuple[object, ...]]]:
    return query(db_url, f"select * from {quote_identifier(table)} limit {limit}")
