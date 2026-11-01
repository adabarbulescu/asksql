from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable, Mapping

from asksql.analysis import AnalysisDefinition, AnalysisEngine
from asksql.models import CancellationToken
from asksql.semantic import SemanticModel
from asksql.service import QueryService


class AnalysisManager:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="asksql-analysis")
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = Lock()

    def start(
        self,
        run_id: str,
        service: QueryService,
        definition: AnalysisDefinition,
        model: SemanticModel,
        inputs: Mapping[str, object],
        *,
        progress: Callable[[list[dict[str, object]], list[dict[str, object]]], None],
        completed: Callable[[dict[str, object]], None],
        failed: Callable[[Exception], None],
    ) -> None:
        token = CancellationToken()
        with self._lock:
            if run_id in self._tokens:
                raise ValueError(f"analysis run is already active: {run_id}")
            self._tokens[run_id] = token

        def execute() -> None:
            try:
                result = AnalysisEngine(service).execute(
                    definition, model, inputs, cancellation=token, progress=progress
                )
                completed(result)
            except Exception as exc:
                failed(exc)
            finally:
                with self._lock:
                    self._tokens.pop(run_id, None)

        self._executor.submit(execute)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(run_id)
        if token is None:
            return False
        token.cancel()
        return True

    def active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._tokens
