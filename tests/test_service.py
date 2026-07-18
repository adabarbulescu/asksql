import unittest

from asksql.demo import create_demo_db
from asksql.models import ExecutionStatus, QueryExecution, QueryResult
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

        execution = QueryExecution("select 1", QueryResult(["1"], [(1,)], False, 200), 0, ExecutionStatus.SUCCEEDED, None)

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
