from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from asksql import sqlite as sqlite_backend
from asksql.adapters.base import format_schema
from asksql.models import CancellationToken, MutationResult, QueryResult, SchemaDetails


class SQLiteAdapter:
    dialect = "sqlite"

    def __init__(self, url: str) -> None:
        self.url = url

    def validate(self) -> int:
        return len(sqlite_backend.inspect(self.url))

    def schema(self, table_names: list[str] | None = None) -> str:
        return format_schema(self.inspect_details(), table_names)

    def inspect_details(self) -> SchemaDetails:
        return sqlite_backend.inspect_details(self.url)

    def query(
        self,
        sql: str,
        limit: int,
        timeout: float | None,
        cancellation: CancellationToken | None,
        parameters: Mapping[str, object] | None = None,
    ) -> QueryResult:
        return sqlite_backend.query_result(self.url, sql, limit, timeout, cancellation, _sqlite_parameters(parameters))

    def execute_write(
        self,
        sql: str,
        timeout: float | None,
        cancellation: CancellationToken | None,
        parameters: Mapping[str, object] | None = None,
    ) -> MutationResult:
        return sqlite_backend.execute_write(self.url, sql, timeout, cancellation, _sqlite_parameters(parameters))

    def explain(self, sql: str) -> QueryResult:
        rows = sqlite_backend.explain_query_plan(self.url, sql)
        return QueryResult(["id", "parent", "notused", "detail"], rows, False, len(rows))


def _sqlite_parameters(parameters: Mapping[str, object] | None) -> dict[str, object]:
    return {name: str(value) if isinstance(value, Decimal) else value for name, value in (parameters or {}).items()}
