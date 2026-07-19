from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from asksql.connections import config_directory
from asksql.models import MutationResult, QueryExecution, QueryResult

WORKSPACE_VERSION = 1


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    connection: str
    question: str | None
    sql: str
    source: str
    model: str | None
    created_at: str
    updated_at: str
    status: str
    duration_ms: float | None
    row_count: int | None
    affected_rows: int | None
    error: str | None
    pinned: bool

    def payload(self) -> dict[str, object]:
        return asdict(self)


class WorkspaceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_directory() / "workspace.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def create_generated(self, connection: str, question: str, sql: str, model: str) -> HistoryEntry:
        return self.create(connection, sql, source="ai", question=question, model=model, status="generated")

    def create(
        self,
        connection: str,
        sql: str,
        *,
        source: str,
        question: str | None = None,
        model: str | None = None,
        status: str = "draft",
    ) -> HistoryEntry:
        if source not in {"ai", "manual"}:
            raise ValueError("history source must be ai or manual")
        identifier = uuid.uuid4().hex
        timestamp = _timestamp()
        with self._connect() as connection_db:
            connection_db.execute(
                """
                insert into history(
                    id, connection_name, question, sql, source, model, created_at, updated_at, status, pinned
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (identifier, connection, question, sql, source, model, timestamp, timestamp, status),
            )
        return self.get(identifier)

    def complete(self, identifier: str, execution: QueryExecution) -> HistoryEntry:
        row_count: int | None = None
        affected_rows: int | None = None
        if isinstance(execution.result, QueryResult):
            row_count = len(execution.result.rows)
        elif isinstance(execution.result, MutationResult):
            affected_rows = execution.result.affected_rows
        with self._connect() as connection:
            cursor = connection.execute(
                """
                update history
                set sql = ?, updated_at = ?, status = ?, duration_ms = ?, row_count = ?, affected_rows = ?, error = ?
                where id = ?
                """,
                (
                    execution.sql,
                    _timestamp(),
                    execution.status.value,
                    execution.duration_ms,
                    row_count,
                    affected_rows,
                    execution.error,
                    identifier,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown history entry: {identifier}")
        return self.get(identifier)

    def get(self, identifier: str) -> HistoryEntry:
        with self._connect() as connection:
            row = connection.execute("select * from history where id = ?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(f"unknown history entry: {identifier}")
        return _history_entry(row)

    def entries(
        self, *, connection_name: str | None = None, search: str | None = None, limit: int = 100
    ) -> list[HistoryEntry]:
        conditions: list[str] = []
        values: list[object] = []
        if connection_name:
            conditions.append("connection_name = ?")
            values.append(connection_name)
        if search:
            conditions.append("(sql like ? escape '\\' or coalesce(question, '') like ? escape '\\')")
            pattern = f"%{_like(search)}%"
            values.extend((pattern, pattern))
        where = f"where {' and '.join(conditions)}" if conditions else ""
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"select * from history {where} order by pinned desc, updated_at desc limit ?", values
            ).fetchall()
        return [_history_entry(row) for row in rows]

    def set_pinned(self, identifier: str, pinned: bool) -> HistoryEntry:
        with self._connect() as connection:
            cursor = connection.execute(
                "update history set pinned = ?, updated_at = ? where id = ?",
                (int(pinned), _timestamp(), identifier),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown history entry: {identifier}")
        return self.get(identifier)

    def delete(self, identifier: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("delete from history where id = ?", (identifier,))
            if cursor.rowcount != 1:
                raise KeyError(f"unknown history entry: {identifier}")

    def clear(self, connection_name: str | None = None) -> int:
        with self._connect() as connection:
            if connection_name:
                cursor = connection.execute("delete from history where connection_name = ?", (connection_name,))
            else:
                cursor = connection.execute("delete from history")
        return max(cursor.rowcount, 0)

    def audit_write(
        self,
        connection_name: str,
        sql: str,
        outcome: str,
        *,
        token_id: str | None = None,
        affected_rows: int | None = None,
        error: str | None = None,
    ) -> str:
        identifier = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """
                insert into write_audit(
                    id, token_id, connection_name, sql, created_at, outcome, affected_rows, error
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (identifier, token_id, connection_name, sql, _timestamp(), outcome, affected_rows, error),
            )
        return identifier

    def complete_write_audit(self, identifier: str, execution: QueryExecution) -> None:
        affected = execution.result.affected_rows if isinstance(execution.result, MutationResult) else None
        with self._connect() as connection:
            cursor = connection.execute(
                "update write_audit set outcome = ?, affected_rows = ?, error = ? where id = ?",
                (execution.status.value, affected, execution.error, identifier),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown write audit entry: {identifier}")

    def write_audit_entries(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("select * from write_audit order by created_at desc").fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists workspace_meta(
                    version integer not null
                );
                create table if not exists history(
                    id text primary key,
                    connection_name text not null,
                    question text,
                    sql text not null,
                    source text not null check(source in ('ai', 'manual')),
                    model text,
                    created_at text not null,
                    updated_at text not null,
                    status text not null,
                    duration_ms real,
                    row_count integer,
                    affected_rows integer,
                    error text,
                    pinned integer not null default 0 check(pinned in (0, 1))
                );
                create index if not exists history_connection_updated
                    on history(connection_name, updated_at desc);
                create table if not exists write_audit(
                    id text primary key,
                    token_id text,
                    connection_name text not null,
                    sql text not null,
                    created_at text not null,
                    outcome text not null,
                    affected_rows integer,
                    error text
                );
                create index if not exists write_audit_created on write_audit(created_at desc);
                """
            )
            row = connection.execute("select version from workspace_meta limit 1").fetchone()
            if row is None:
                connection.execute("insert into workspace_meta(version) values (?)", (WORKSPACE_VERSION,))
            elif row[0] != WORKSPACE_VERSION:
                raise RuntimeError(f"unsupported workspace database version: {row[0]}")
        os.chmod(self.path, 0o600)


def _history_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=str(row["id"]),
        connection=str(row["connection_name"]),
        question=row["question"],
        sql=str(row["sql"]),
        source=str(row["source"]),
        model=row["model"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        status=str(row["status"]),
        duration_ms=row["duration_ms"],
        row_count=row["row_count"],
        affected_rows=row["affected_rows"],
        error=row["error"],
        pinned=bool(row["pinned"]),
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
