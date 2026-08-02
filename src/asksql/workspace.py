from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from asksql.connections import config_directory
from asksql.models import ExecutionStatus, MutationResult, QueryExecution, QueryResult

WORKSPACE_VERSION = 2

DOCUMENT_STATES = {"draft", "generated", "running", "completed", "failed", "cancelled"}


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


@dataclass(frozen=True)
class QueryDocument:
    id: str
    title: str
    connection: str
    selected_tables: list[str]
    question: str
    generated_sql: str
    edited_sql: str
    lifecycle_state: str
    execution_status: str | None
    duration_ms: float | None
    row_count: int | None
    error: str | None
    result_reference: str | None
    created_at: str
    updated_at: str

    def payload(self) -> dict[str, object]:
        return asdict(self)


class WorkspaceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_directory() / "workspace.db"
        existed = self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate(existed)

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

    def workspace(self) -> dict[str, object]:
        with self._connect() as connection:
            state = connection.execute("select * from workspace_state where id = 1").fetchone()
            rows = connection.execute("select * from query_documents order by position, created_at").fetchall()
        documents = [_query_document(row) for row in rows]
        return {
            "activeConnection": state["active_connection"] if state else None,
            "activeDocumentId": state["active_document_id"] if state else None,
            "documents": [document.payload() for document in documents],
        }

    def update_workspace(
        self, *, active_connection: str | None = None, active_document_id: str | None = None
    ) -> dict[str, object]:
        with self._connect() as connection:
            if active_document_id is not None:
                exists = connection.execute(
                    "select 1 from query_documents where id = ?", (active_document_id,)
                ).fetchone()
                if exists is None:
                    raise KeyError(f"unknown query document: {active_document_id}")
            connection.execute(
                """
                update workspace_state
                set active_connection = coalesce(?, active_connection),
                    active_document_id = coalesce(?, active_document_id), updated_at = ?
                where id = 1
                """,
                (active_connection, active_document_id, _timestamp()),
            )
        return self.workspace()

    def create_document(
        self,
        connection_name: str,
        *,
        title: str = "Untitled query",
        question: str = "",
        edited_sql: str = "select 1 as ready",
        selected_tables: list[str] | None = None,
    ) -> QueryDocument:
        identifier = uuid.uuid4().hex
        timestamp = _timestamp()
        with self._connect() as connection:
            position = connection.execute("select coalesce(max(position), -1) + 1 from query_documents").fetchone()[0]
            connection.execute(
                """
                insert into query_documents(
                    id, title, connection_name, selected_tables, question, generated_sql, edited_sql,
                    lifecycle_state, position, created_at, updated_at
                ) values (?, ?, ?, ?, ?, '', ?, 'draft', ?, ?, ?)
                """,
                (
                    identifier,
                    _document_title(title),
                    connection_name,
                    _tables_json(selected_tables or []),
                    question,
                    edited_sql,
                    position,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "update workspace_state set active_connection = ?, active_document_id = ?, updated_at = ? where id = 1",
                (connection_name, identifier, timestamp),
            )
        return self.get_document(identifier)

    def get_document(self, identifier: str) -> QueryDocument:
        with self._connect() as connection:
            row = connection.execute("select * from query_documents where id = ?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(f"unknown query document: {identifier}")
        return _query_document(row)

    def update_document(self, identifier: str, **changes: object) -> QueryDocument:
        allowed = {
            "title": "title",
            "connection": "connection_name",
            "selected_tables": "selected_tables",
            "question": "question",
            "generated_sql": "generated_sql",
            "edited_sql": "edited_sql",
            "lifecycle_state": "lifecycle_state",
            "execution_status": "execution_status",
            "duration_ms": "duration_ms",
            "row_count": "row_count",
            "error": "error",
            "result_reference": "result_reference",
        }
        assignments: list[str] = []
        values: list[object] = []
        for name, value in changes.items():
            column = allowed.get(name)
            if column is None:
                raise ValueError(f"unsupported query document field: {name}")
            if name == "title":
                value = _document_title(str(value))
            elif name == "selected_tables":
                value = _tables_json(value if isinstance(value, list) else [])
            elif name == "lifecycle_state" and value not in DOCUMENT_STATES:
                raise ValueError(f"invalid query document state: {value}")
            assignments.append(f"{column} = ?")
            values.append(value)
        if not assignments:
            return self.get_document(identifier)
        assignments.append("updated_at = ?")
        values.extend((_timestamp(), identifier))
        with self._connect() as connection:
            cursor = connection.execute(
                f"update query_documents set {', '.join(assignments)} where id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown query document: {identifier}")
        return self.get_document(identifier)

    def complete_document(self, identifier: str, execution: QueryExecution, result_reference: str) -> QueryDocument:
        row_count = len(execution.result.rows) if isinstance(execution.result, QueryResult) else None
        if execution.status == ExecutionStatus.SUCCEEDED:
            state = "completed"
        elif execution.status == ExecutionStatus.CANCELLED:
            state = "cancelled"
        else:
            state = "failed"
        return self.update_document(
            identifier,
            edited_sql=execution.sql,
            lifecycle_state=state,
            execution_status=execution.status.value,
            duration_ms=execution.duration_ms,
            row_count=row_count,
            error=execution.error,
            result_reference=result_reference,
        )

    def delete_document(self, identifier: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("delete from query_documents where id = ?", (identifier,))
            if cursor.rowcount != 1:
                raise KeyError(f"unknown query document: {identifier}")
            next_row = connection.execute(
                "select id, connection_name from query_documents order by position, created_at limit 1"
            ).fetchone()
            connection.execute(
                "update workspace_state set active_document_id = ?, active_connection = ?, updated_at = ? where id = 1",
                (
                    next_row["id"] if next_row else None,
                    next_row["connection_name"] if next_row else None,
                    _timestamp(),
                ),
            )

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

    def _migrate(self, existed: bool) -> None:
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
                create table if not exists workspace_state(
                    id integer primary key check(id = 1),
                    active_connection text,
                    active_document_id text,
                    updated_at text not null
                );
                create table if not exists query_documents(
                    id text primary key,
                    title text not null,
                    connection_name text not null,
                    selected_tables text not null default '[]',
                    question text not null default '',
                    generated_sql text not null default '',
                    edited_sql text not null default '',
                    lifecycle_state text not null,
                    execution_status text,
                    duration_ms real,
                    row_count integer,
                    error text,
                    result_reference text,
                    position integer not null,
                    created_at text not null,
                    updated_at text not null
                );
                create index if not exists query_documents_updated on query_documents(updated_at desc);
                """
            )
            row = connection.execute("select version from workspace_meta limit 1").fetchone()
            if row is None:
                if existed:
                    self._backup("pre-migration")
                connection.execute("insert into workspace_meta(version) values (?)", (WORKSPACE_VERSION,))
            elif row[0] == 1:
                self._backup("pre-v2")
                connection.execute("update workspace_meta set version = ?", (WORKSPACE_VERSION,))
            elif row[0] != WORKSPACE_VERSION:
                backup = self._backup(f"unsupported-v{row[0]}")
                raise RuntimeError(f"unsupported workspace database version: {row[0]}. Backup created at {backup}")
            connection.execute(
                "insert or ignore into workspace_state(id, updated_at) values (1, ?)", (_timestamp(),)
            )
            connection.execute(
                """
                update query_documents
                set lifecycle_state = 'cancelled', execution_status = 'cancelled',
                    error = 'Execution interrupted when Studio stopped', updated_at = ?
                where lifecycle_state = 'running'
                """,
                (_timestamp(),),
            )
        os.chmod(self.path, 0o600)

    def _backup(self, reason: str) -> Path:
        target = self.path.with_name(f"{self.path.name}.{reason}.bak")
        index = 1
        while target.exists():
            target = self.path.with_name(f"{self.path.name}.{reason}.{index}.bak")
            index += 1
        shutil.copy2(self.path, target)
        os.chmod(target, 0o600)
        return target


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


def _query_document(row: sqlite3.Row) -> QueryDocument:
    import json

    return QueryDocument(
        id=str(row["id"]),
        title=str(row["title"]),
        connection=str(row["connection_name"]),
        selected_tables=list(json.loads(row["selected_tables"])),
        question=str(row["question"]),
        generated_sql=str(row["generated_sql"]),
        edited_sql=str(row["edited_sql"]),
        lifecycle_state=str(row["lifecycle_state"]),
        execution_status=row["execution_status"],
        duration_ms=row["duration_ms"],
        row_count=row["row_count"],
        error=row["error"],
        result_reference=row["result_reference"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _document_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise ValueError("query document title cannot be empty")
    return title[:200]


def _tables_json(tables: list[object]) -> str:
    import json

    return json.dumps([str(table) for table in tables], separators=(",", ":"))


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
