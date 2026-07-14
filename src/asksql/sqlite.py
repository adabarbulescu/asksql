from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse


Column = tuple[str, str, bool]


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
    with sqlite3.connect(read_only_uri(db_url), uri=True) as conn:
        cursor = conn.execute(sql)
        return [col[0] for col in cursor.description or []], cursor.fetchmany(200)
