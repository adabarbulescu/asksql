from __future__ import annotations

from urllib.parse import urlparse

from asksql.adapters.base import DatabaseAdapter
from asksql.adapters.postgres import PostgreSQLAdapter
from asksql.adapters.sqlite import SQLiteAdapter


def adapter_for(url: str) -> DatabaseAdapter:
    scheme = urlparse(url).scheme.lower()
    if scheme == "sqlite":
        return SQLiteAdapter(url)
    if scheme in {"postgres", "postgresql"}:
        return PostgreSQLAdapter(url)
    raise ValueError(f"unsupported database URL scheme: {scheme or '(missing)'}")
