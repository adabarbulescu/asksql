from __future__ import annotations

import time

from asksql.adapters import adapter_for
from asksql.llm import generate_sql
from asksql.models import (
    CancellationToken,
    ExecutionStatus,
    GeneratedQuery,
    MutationResult,
    QueryCancelledError,
    QueryExecution,
    QueryResult,
    QueryTimeoutError,
)
from asksql.safety import is_read_only, is_write
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, query_result


class QueryService:
    def __init__(self, db_url: str, model: str = "") -> None:
        self.db_url = db_url
        self.model = model
        self.adapter = adapter_for(db_url)

    def generate(self, question: str, tables: list[str] | None = None) -> GeneratedQuery:
        sql = generate_sql(self.model, self.adapter.schema(tables), question, self.adapter.dialect)
        return GeneratedQuery(question, sql, self.model)

    def execute(
        self,
        sql: str,
        *,
        limit: int = DEFAULT_LIMIT,
        timeout: float | None = DEFAULT_TIMEOUT,
        cancellation: CancellationToken | None = None,
        allow_write: bool = False,
    ) -> QueryExecution:
        started = time.monotonic()
        read_only = is_read_only(sql, self.adapter.dialect)
        write = is_write(sql, self.adapter.dialect)
        if not read_only and not (allow_write and write):
            message = (
                "Write SQL requires the explicit --write option." if write else "Refusing unsupported or unsafe SQL."
            )
            return self._execution(sql, started, ExecutionStatus.REFUSED, message)
        try:
            result: QueryResult | MutationResult
            if read_only and self.adapter.dialect == "sqlite":
                # Keep this stable seam for CLI integrations that patch the legacy executor.
                result = query_result(self.db_url, sql, limit, timeout, cancellation)
            elif read_only:
                result = self.adapter.query(sql, limit, timeout, cancellation)
            else:
                result = self.adapter.execute_write(sql, timeout, cancellation)
        except QueryTimeoutError as exc:
            return self._execution(sql, started, ExecutionStatus.TIMED_OUT, str(exc))
        except QueryCancelledError as exc:
            return self._execution(sql, started, ExecutionStatus.CANCELLED, str(exc))
        except Exception as exc:
            return self._execution(sql, started, ExecutionStatus.FAILED, str(exc))
        return QueryExecution(sql, result, (time.monotonic() - started) * 1000, ExecutionStatus.SUCCEEDED, None)

    def _execution(self, sql: str, started: float, status: ExecutionStatus, error: str) -> QueryExecution:
        return QueryExecution(sql, None, (time.monotonic() - started) * 1000, status, error)
