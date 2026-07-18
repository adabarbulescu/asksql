from __future__ import annotations

import time

from asksql.llm import generate_sql
from asksql.models import (
    CancellationToken,
    ExecutionStatus,
    GeneratedQuery,
    QueryCancelledError,
    QueryExecution,
    QueryTimeoutError,
)
from asksql.safety import is_read_only
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, query_result, schema


class QueryService:
    def __init__(self, db_url: str, model: str = "") -> None:
        self.db_url = db_url
        self.model = model

    def generate(self, question: str) -> GeneratedQuery:
        return GeneratedQuery(question, generate_sql(self.model, schema(self.db_url), question), self.model)

    def execute(
        self,
        sql: str,
        *,
        limit: int = DEFAULT_LIMIT,
        timeout: float | None = DEFAULT_TIMEOUT,
        cancellation: CancellationToken | None = None,
    ) -> QueryExecution:
        started = time.monotonic()
        if not is_read_only(sql):
            return self._execution(sql, started, ExecutionStatus.REFUSED, "Refusing to run non-read-only SQL.")
        try:
            result = query_result(self.db_url, sql, limit, timeout, cancellation)
        except QueryTimeoutError as exc:
            return self._execution(sql, started, ExecutionStatus.TIMED_OUT, str(exc))
        except QueryCancelledError as exc:
            return self._execution(sql, started, ExecutionStatus.CANCELLED, str(exc))
        except Exception as exc:
            return self._execution(sql, started, ExecutionStatus.FAILED, str(exc))
        return QueryExecution(sql, result, (time.monotonic() - started) * 1000, ExecutionStatus.SUCCEEDED, None)

    def _execution(self, sql: str, started: float, status: ExecutionStatus, error: str) -> QueryExecution:
        return QueryExecution(sql, None, (time.monotonic() - started) * 1000, status, error)
