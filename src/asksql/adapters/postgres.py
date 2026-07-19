from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from asksql.adapters.base import format_schema
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


class PostgreSQLAdapter:
    dialect = "postgres"

    def __init__(self, url: str) -> None:
        self.url = url

    def validate(self) -> int:
        with self._connection(read_only=True) as connection:
            row = connection.execute(
                "select count(*) from information_schema.tables where table_schema = current_schema()"
            ).fetchone()
            return int(row[0])

    def schema(self, table_names: list[str] | None = None) -> str:
        return format_schema(self.inspect_details(), table_names)

    def inspect_details(self) -> SchemaDetails:
        with self._connection(read_only=True) as connection:
            table_rows = connection.execute(
                """
                select c.relname, greatest(c.reltuples::bigint, 0)
                from pg_class c join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = current_schema() and c.relkind = 'r'
                order by c.relname
                """
            ).fetchall()
            tables: dict[str, TableSchema] = {}
            for name, estimate in table_rows:
                columns = connection.execute(
                    """
                    select c.column_name, c.data_type,
                           exists (
                             select 1 from information_schema.table_constraints tc
                             join information_schema.key_column_usage kcu
                               on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
                             where tc.constraint_type = 'PRIMARY KEY' and tc.table_schema = current_schema()
                               and tc.table_name = %s and kcu.column_name = c.column_name
                           )
                    from information_schema.columns c
                    where c.table_schema = current_schema() and c.table_name = %s
                    order by c.ordinal_position
                    """,
                    (name, name),
                ).fetchall()
                foreign_keys = connection.execute(
                    """
                    select kcu.column_name, ccu.table_name, ccu.column_name
                    from information_schema.table_constraints tc
                    join information_schema.key_column_usage kcu
                      on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
                    join information_schema.constraint_column_usage ccu
                      on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
                    where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = current_schema()
                      and tc.table_name = %s
                    """,
                    (name,),
                ).fetchall()
                index_rows = connection.execute(
                    "select indexname, indexdef from pg_indexes where schemaname = current_schema() and tablename = %s",
                    (name,),
                ).fetchall()
                indexes = [
                    IndexSchema(index_name, _index_columns(definition), " UNIQUE INDEX " in definition.upper())
                    for index_name, definition in index_rows
                ]
                tables[str(name)] = TableSchema(
                    str(name),
                    [Column(str(row[0]), str(row[1]), bool(row[2])) for row in columns],
                    [ForeignKey(str(row[0]), str(row[1]), str(row[2])) for row in foreign_keys],
                    indexes,
                    int(estimate),
                )
            views = [
                DatabaseObject(str(row[0]), "view", None, str(row[1]))
                for row in connection.execute(
                    "select viewname, definition from pg_views where schemaname = current_schema() order by viewname"
                ).fetchall()
            ]
            triggers = [
                DatabaseObject(str(row[0]), "trigger", str(row[1]), str(row[2]))
                for row in connection.execute(
                    """
                    select trigger_name, event_object_table, action_statement
                    from information_schema.triggers where trigger_schema = current_schema()
                    order by trigger_name
                    """
                ).fetchall()
            ]
        return SchemaDetails(tables, views, triggers)

    def query(self, sql: str, limit: int, timeout: float | None, cancellation: CancellationToken | None) -> QueryResult:
        try:
            with self._connection(read_only=True, timeout=timeout, cancellation=cancellation) as connection:
                cursor = connection.execute(sql)
                rows = cursor.fetchmany(limit + 1)
                columns = [column.name for column in cursor.description or []]
                return QueryResult(columns, rows[:limit], len(rows) > limit, limit)
        except Exception as exc:
            self._translate_error(exc, cancellation, timeout)
            raise

    def execute_write(self, sql: str, timeout: float | None, cancellation: CancellationToken | None) -> MutationResult:
        try:
            with self._connection(read_only=False, timeout=timeout, cancellation=cancellation) as connection:
                cursor = connection.execute(sql)
                return MutationResult(max(cursor.rowcount, 0), None)
        except Exception as exc:
            self._translate_error(exc, cancellation, timeout)
            raise

    def explain(self, sql: str) -> QueryResult:
        with self._connection(read_only=True) as connection:
            cursor = connection.execute(f"explain (format json) {sql}")
            rows = cursor.fetchall()
            return QueryResult(["plan"], rows, False, len(rows))

    @contextmanager
    def _connection(
        self,
        *,
        read_only: bool,
        timeout: float | None = None,
        cancellation: CancellationToken | None = None,
    ) -> Iterator[Any]:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires: pip install 'asksql[postgres]'") from exc
        with psycopg.connect(self.url) as connection:
            if read_only:
                connection.execute("set transaction read only")
            if timeout is not None:
                connection.execute(
                    "select set_config('statement_timeout', %s, true)", (str(max(1, int(timeout * 1000))),)
                )
            remove = cancellation.add_callback(connection.cancel) if cancellation else None
            try:
                yield connection
            finally:
                if remove:
                    remove()

    @staticmethod
    def _translate_error(exc: Exception, cancellation: CancellationToken | None, timeout: float | None) -> None:
        if cancellation and cancellation.cancelled:
            raise QueryCancelledError("query cancelled") from exc
        if getattr(exc, "sqlstate", None) == "57014" and timeout is not None:
            raise QueryTimeoutError(f"query timed out after {timeout:g} seconds") from exc


def _index_columns(definition: str) -> list[str]:
    tail = definition.rsplit("(", 1)[-1].rstrip(")")
    return [part.strip().strip('"') for part in tail.split(",")]
