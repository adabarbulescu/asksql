import time
import unittest
from unittest.mock import MagicMock

from asksql.models import ExecutionStatus, QueryExecution, QueryResult
from asksql.studio.jobs import ExecutionManager


class ExecutionManagerTest(unittest.TestCase):
    def test_runs_job_and_calls_completion_hook(self) -> None:
        execution = QueryExecution(
            "select 1", QueryResult(["1"], [(1,)], False, 200), 1, ExecutionStatus.SUCCEEDED, None
        )
        service = MagicMock()
        service.execute.return_value = execution
        completed = MagicMock()
        manager = ExecutionManager(max_workers=1)

        job = manager.start(service, "select 1", "history", limit=200, timeout=30, completed=completed)
        deadline = time.monotonic() + 2
        while manager.get(job.id).state != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(manager.get(job.id).execution, execution)
        completed.assert_called_once_with(execution)

    def test_cancel_signals_token(self) -> None:
        manager = ExecutionManager(max_workers=1)
        service = MagicMock()
        service.execute.return_value = QueryExecution(
            "select 1", QueryResult(["1"], [(1,)], False, 200), 1, ExecutionStatus.SUCCEEDED, None
        )
        job = manager.start(service, "select 1", "history", limit=200, timeout=30)

        manager.cancel(job.id)

        self.assertTrue(job.token.cancelled)


if __name__ == "__main__":
    unittest.main()
