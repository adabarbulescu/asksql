from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from asksql.models import CancellationToken, QueryExecution
from asksql.service import QueryService


@dataclass
class ExecutionJob:
    id: str
    history_id: str
    state: str
    token: CancellationToken
    execution: QueryExecution | None = None


class ExecutionManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="asksql-studio")
        self._jobs: dict[str, ExecutionJob] = {}
        self._lock = Lock()

    def start(
        self,
        service: QueryService,
        sql: str,
        history_id: str,
        *,
        limit: int,
        timeout: float,
        allow_write: bool = False,
        completed: Callable[[QueryExecution], None] | None = None,
    ) -> ExecutionJob:
        job = ExecutionJob(uuid.uuid4().hex, history_id, "queued", CancellationToken())
        with self._lock:
            self._jobs[job.id] = job

        def run() -> None:
            with self._lock:
                job.state = "running"
            execution = service.execute(
                sql,
                limit=limit,
                timeout=timeout,
                cancellation=job.token,
                allow_write=allow_write,
            )
            try:
                if completed:
                    completed(execution)
            finally:
                with self._lock:
                    job.execution = execution
                    job.state = "completed"

        self._executor.submit(run)
        return job

    def get(self, identifier: str) -> ExecutionJob:
        with self._lock:
            job = self._jobs.get(identifier)
        if job is None:
            raise KeyError(f"unknown execution job: {identifier}")
        return job

    def cancel(self, identifier: str) -> ExecutionJob:
        job = self.get(identifier)
        job.token.cancel()
        return job
