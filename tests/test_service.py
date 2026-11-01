import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from asksql.demo import create_demo_db
from asksql.models import (
    AutoFixAttempt,
    CancellationToken,
    ExecutionStatus,
    MutationResult,
    QueryExecution,
    QueryResult,
)
from asksql.service import QueryService


class QueryServiceTest(unittest.TestCase):
    def test_execute_success(self) -> None:
        execution = QueryService(create_demo_db()).execute("select id from customers order by id limit 1")

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.result.rows, [(1,)])
        self.assertGreaterEqual(execution.duration_ms, 0)

    def test_execute_refuses_write_sql(self) -> None:
        execution = QueryService(create_demo_db()).execute("delete from customers")

        self.assertEqual(execution.status, ExecutionStatus.REFUSED)
        self.assertIsNone(execution.result)

    def test_execute_commits_write_only_with_explicit_opt_in(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="asksql-service-", suffix=".db", delete=False) as file:
            path = Path(file.name)
        with sqlite3.connect(path) as conn:
            conn.execute("create table items(id integer primary key, name text)")
        service = QueryService(f"sqlite://{path}")

        execution = service.execute("insert into items(name) values ('committed')", allow_write=True)

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertIsInstance(execution.result, MutationResult)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute("select name from items").fetchall(), [("committed",)])

    def test_execute_reports_timeout(self) -> None:
        sql = """
        with recursive nums(n) as (
            select 1
            union all
            select n + 1 from nums where n < 100000000
        )
        select sum(a.n + b.n)
        from nums a, nums b
        """

        execution = QueryService(create_demo_db()).execute(sql, timeout=0.001)

        self.assertEqual(execution.status, ExecutionStatus.TIMED_OUT)
        self.assertIsNone(execution.result)

    def test_query_execution_invariants(self) -> None:
        with self.assertRaises(ValueError):
            QueryExecution("select 1", None, 0, ExecutionStatus.SUCCEEDED, None)
        with self.assertRaises(ValueError):
            QueryExecution("select 1", None, 0, ExecutionStatus.FAILED, None)
        with self.assertRaises(ValueError):
            QueryExecution("select 1", QueryResult(["1"], [(1,)], False, 200), 0, ExecutionStatus.SUCCEEDED, "oops")
        with self.assertRaises(ValueError):
            QueryExecution("select 1", QueryResult(["1"], [(1,)], False, 200), 0, ExecutionStatus.FAILED, "failed")
        with self.assertRaises(ValueError):
            QueryExecution("select 1", QueryResult(["1"], [(1,)], False, 200), -1, ExecutionStatus.SUCCEEDED, None)

        execution = QueryExecution(
            "select 1", QueryResult(["1"], [(1,)], False, 200), 0, ExecutionStatus.SUCCEEDED, None
        )

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)

    def test_cancellation_token_cancel_is_idempotent(self) -> None:
        token = CancellationToken()
        calls = []
        token.add_callback(lambda: calls.append("cancelled"))

        token.cancel()
        token.cancel()

        self.assertEqual(calls, ["cancelled"])

    def test_autofix_attempt_invariants(self) -> None:
        with self.assertRaises(ValueError):
            AutoFixAttempt(0, "select 1", None, ExecutionStatus.SUCCEEDED)
        with self.assertRaises(ValueError):
            AutoFixAttempt(1, "select 1", None, ExecutionStatus.SUCCEEDED, duration_ms=-1)

        attempt = AutoFixAttempt(1, "select 1", None, ExecutionStatus.SUCCEEDED, duration_ms=10.5)
        self.assertEqual(attempt.attempt, 1)

    def test_execute_with_repair_success_without_retries(self) -> None:
        service = QueryService(create_demo_db())
        execution = service.execute_with_repair(
            "get first customer",
            "select id from customers order by id limit 1",
            max_retries=2,
        )
        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.attempts, [])

    def test_execute_with_repair_recovers_from_error(self) -> None:
        service = QueryService(create_demo_db())
        # repair mock will return valid SQL
        with patch.object(
            service,
            "repair",
            return_value=MagicMock(sql="select id from customers order by id limit 1"),
        ) as mock_repair:
            execution = service.execute_with_repair(
                "get first customer",
                "select id from non_existent_table limit 1",
                max_retries=2,
            )

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(len(execution.attempts), 2)
        self.assertEqual(execution.attempts[0].attempt, 1)
        self.assertEqual(execution.attempts[0].status, ExecutionStatus.FAILED)
        self.assertEqual(execution.attempts[1].attempt, 2)
        self.assertEqual(execution.attempts[1].status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.sql, "select id from customers order by id limit 1")
        mock_repair.assert_called_once()

    def test_execute_with_repair_exhausts_retries(self) -> None:
        service = QueryService(create_demo_db())
        with patch.object(
            service,
            "repair",
            return_value=MagicMock(sql="select * from still_broken"),
        ):
            execution = service.execute_with_repair(
                "broken query",
                "select * from broken_table",
                max_retries=2,
            )

        self.assertEqual(execution.status, ExecutionStatus.FAILED)
        self.assertEqual(len(execution.attempts), 3)  # initial + 2 retries
        self.assertEqual([a.attempt for a in execution.attempts], [1, 2, 3])

    def test_execute_with_repair_refuses_unsafe_repair(self) -> None:
        service = QueryService(create_demo_db())
        with patch.object(
            service,
            "repair",
            return_value=MagicMock(sql="delete from customers"),
        ):
            execution = service.execute_with_repair(
                "delete query",
                "select * from non_existent",
                max_retries=2,
            )

        self.assertEqual(execution.status, ExecutionStatus.REFUSED)
        self.assertEqual(len(execution.attempts), 2)
        self.assertEqual(execution.attempts[1].status, ExecutionStatus.REFUSED)

    def test_execute_with_repair_does_not_retry_timeout(self) -> None:
        service = QueryService(create_demo_db())
        sql = """
        with recursive nums(n) as (
            select 1
            union all
            select n + 1 from nums where n < 100000000
        )
        select sum(a.n + b.n)
        from nums a, nums b
        """
        with patch.object(service, "repair") as mock_repair:
            execution = service.execute_with_repair("slow query", sql, timeout=0.001, max_retries=2)

        self.assertEqual(execution.status, ExecutionStatus.TIMED_OUT)
        mock_repair.assert_not_called()

    def test_execute_with_repair_respects_cancellation(self) -> None:
        service = QueryService(create_demo_db())
        token = CancellationToken()
        token.cancel()
        execution = service.execute_with_repair(
            "test query",
            "select * from broken",
            cancellation=token,
            max_retries=2,
        )
        self.assertEqual(execution.status, ExecutionStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
