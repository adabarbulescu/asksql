from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Event, Lock
from typing import Callable


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool


@dataclass(frozen=True)
class ForeignKey:
    column: str
    referenced_table: str
    referenced_column: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: list[Column]
    foreign_keys: list[ForeignKey]


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[object, ...]]
    truncated: bool
    limit: int


@dataclass(frozen=True)
class MutationResult:
    affected_rows: int
    last_insert_id: int | None = None

    def __post_init__(self) -> None:
        if self.affected_rows < 0:
            raise ValueError("affected rows cannot be negative")


@dataclass(frozen=True)
class GeneratedQuery:
    question: str
    sql: str
    model: str


class ExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class QueryExecution:
    sql: str
    result: QueryResult | MutationResult | None
    duration_ms: float
    status: ExecutionStatus
    error: str | None

    def __post_init__(self) -> None:
        succeeded = self.status == ExecutionStatus.SUCCEEDED
        if succeeded and self.result is None:
            raise ValueError("successful execution requires a result")
        if succeeded and self.error is not None:
            raise ValueError("successful execution cannot contain an error")
        if not succeeded and self.result is not None:
            raise ValueError("unsuccessful execution cannot contain a result")
        if not succeeded and self.error is None:
            raise ValueError("unsuccessful execution requires an error")
        if self.duration_ms < 0:
            raise ValueError("execution duration cannot be negative")


class QueryTimeoutError(Exception):
    pass


class QueryCancelledError(Exception):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = Lock()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        with self._lock:
            if self._cancelled.is_set():
                return
            self._cancelled.set()
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback()

    def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            if self.cancelled:
                callback()
                return lambda: None
            self._callbacks.append(callback)

        def remove() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return remove
