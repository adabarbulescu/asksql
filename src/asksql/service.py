from __future__ import annotations

import time
from typing import Callable, Mapping

from asksql.adapters import adapter_for
from asksql.llm import generate_sql, repair_sql
from asksql.models import (
    AutoFixAttempt,
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

    def generate(
        self, question: str, tables: list[str] | None = None, semantic_context: str | None = None
    ) -> GeneratedQuery:
        schema = self.adapter.schema(tables)
        if semantic_context:
            schema = f"{schema}\n\n{semantic_context}"
        sql = generate_sql(self.model, schema, question, self.adapter.dialect)
        return GeneratedQuery(question, sql, self.model)

    def repair(
        self,
        question: str,
        failed_sql: str,
        error: str,
        tables: list[str] | None = None,
        model: str | None = None,
    ) -> GeneratedQuery:
        target_model = model or self.model
        schema = self.adapter.schema(tables)
        sql = repair_sql(target_model, schema, question, failed_sql, error, self.adapter.dialect)
        return GeneratedQuery(question, sql, target_model)

    def execute(
        self,
        sql: str,
        *,
        limit: int = DEFAULT_LIMIT,
        timeout: float | None = DEFAULT_TIMEOUT,
        cancellation: CancellationToken | None = None,
        allow_write: bool = False,
        parameters: Mapping[str, object] | None = None,
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
            if read_only and self.adapter.dialect == "sqlite" and not parameters:
                # Keep this stable seam for CLI integrations that patch the legacy executor.
                result = query_result(self.db_url, sql, limit, timeout, cancellation, parameters)
            elif read_only:
                result = self.adapter.query(sql, limit, timeout, cancellation, parameters)
            else:
                result = self.adapter.execute_write(sql, timeout, cancellation, parameters)
        except QueryTimeoutError as exc:
            return self._execution(sql, started, ExecutionStatus.TIMED_OUT, str(exc))
        except QueryCancelledError as exc:
            return self._execution(sql, started, ExecutionStatus.CANCELLED, str(exc))
        except Exception as exc:
            return self._execution(sql, started, ExecutionStatus.FAILED, str(exc))
        return QueryExecution(sql, result, (time.monotonic() - started) * 1000, ExecutionStatus.SUCCEEDED, None)

    def execute_with_repair(
        self,
        question: str,
        sql: str,
        *,
        limit: int = DEFAULT_LIMIT,
        timeout: float | None = DEFAULT_TIMEOUT,
        cancellation: CancellationToken | None = None,
        max_retries: int = 2,
        tables: list[str] | None = None,
        on_repair_attempt: Callable[[AutoFixAttempt], None] | None = None,
        parameters: Mapping[str, object] | None = None,
    ) -> QueryExecution:
        started = time.monotonic()
        execution = self.execute(
            sql,
            limit=limit,
            timeout=timeout,
            cancellation=cancellation,
            allow_write=False,
            parameters=parameters,
        )
        if execution.status != ExecutionStatus.FAILED or max_retries <= 0:
            return execution

        attempts: list[AutoFixAttempt] = [
            AutoFixAttempt(
                attempt=1,
                sql=execution.sql,
                error=execution.error,
                status=execution.status,
                duration_ms=execution.duration_ms,
            )
        ]
        if on_repair_attempt:
            on_repair_attempt(attempts[0])

        current_sql = sql
        current_error = execution.error or "Unknown database error"

        for retry_idx in range(1, max_retries + 1):
            if cancellation and cancellation.cancelled:
                return QueryExecution(
                    current_sql,
                    None,
                    (time.monotonic() - started) * 1000,
                    ExecutionStatus.CANCELLED,
                    "Query cancelled",
                    attempts=attempts,
                )

            try:
                repaired = self.repair(question, current_sql, current_error, tables)
                repaired_sql = repaired.sql
            except Exception as exc:
                return QueryExecution(
                    current_sql,
                    None,
                    (time.monotonic() - started) * 1000,
                    ExecutionStatus.FAILED,
                    f"Auto-fix repair failed: {exc}",
                    attempts=attempts,
                )

            if cancellation and cancellation.cancelled:
                return QueryExecution(
                    repaired_sql,
                    None,
                    (time.monotonic() - started) * 1000,
                    ExecutionStatus.CANCELLED,
                    "Query cancelled",
                    attempts=attempts,
                )

            repair_exec = self.execute(
                repaired_sql,
                limit=limit,
                timeout=timeout,
                cancellation=cancellation,
                allow_write=False,
                parameters=parameters,
            )
            attempt_record = AutoFixAttempt(
                attempt=retry_idx + 1,
                sql=repaired_sql,
                error=repair_exec.error,
                status=repair_exec.status,
                duration_ms=repair_exec.duration_ms,
            )
            attempts.append(attempt_record)
            if on_repair_attempt:
                on_repair_attempt(attempt_record)

            if repair_exec.status == ExecutionStatus.SUCCEEDED:
                return QueryExecution(
                    repaired_sql,
                    repair_exec.result,
                    (time.monotonic() - started) * 1000,
                    ExecutionStatus.SUCCEEDED,
                    None,
                    attempts=attempts,
                )

            if repair_exec.status != ExecutionStatus.FAILED:
                return QueryExecution(
                    repaired_sql,
                    None,
                    (time.monotonic() - started) * 1000,
                    repair_exec.status,
                    repair_exec.error,
                    attempts=attempts,
                )

            current_sql = repaired_sql
            current_error = repair_exec.error or "Unknown database error"

        return QueryExecution(
            current_sql,
            None,
            (time.monotonic() - started) * 1000,
            ExecutionStatus.FAILED,
            current_error,
            attempts=attempts,
        )

    def _execution(self, sql: str, started: float, status: ExecutionStatus, error: str) -> QueryExecution:
        return QueryExecution(sql, None, (time.monotonic() - started) * 1000, status, error)
