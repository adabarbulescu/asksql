import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.demo import create_demo_db
from asksql.sqlite import DEFAULT_LIMIT, inspect, limited_query, preview_table, query_result, quote_identifier


class SqliteTest(unittest.TestCase):
    def test_inspect_demo_schema(self) -> None:
        tables = inspect(create_demo_db())
        self.assertEqual(tables["customers"][0], ("id", "INTEGER", True))
        self.assertIn("orders", tables)

    def test_preview_table(self) -> None:
        columns, rows = preview_table(create_demo_db(), "customers", 1)
        self.assertEqual(columns, ["id", "name", "email", "created_at"])
        self.assertEqual(rows[0][1], "Ada")

    def test_limited_query_reports_truncation(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="asksql-test-", suffix=".db", delete=False) as file:
            path = Path(file.name)
        with sqlite3.connect(path) as conn:
            conn.execute("create table items(id integer)")
            conn.executemany("insert into items values (?)", [(1,), (2,)])

        columns, rows, truncated = limited_query(f"sqlite://{path}", "select id from items order by id", limit=1)

        self.assertEqual(columns, ["id"])
        self.assertEqual(rows, [(1,)])
        self.assertTrue(truncated)

    def test_query_result_default_limit(self) -> None:
        result = query_result(create_demo_db(), "select id from customers order by id")

        self.assertEqual(result.limit, DEFAULT_LIMIT)

    def test_query_result_uses_configured_limit(self) -> None:
        result = query_result(create_demo_db(), "select id from customers order by id", limit=1)

        self.assertEqual(result.limit, 1)
        self.assertEqual(result.rows, [(1,)])
        self.assertTrue(result.truncated)

    def test_quote_identifier(self) -> None:
        self.assertEqual(quote_identifier('weird"name'), '"weird""name"')


if __name__ == "__main__":
    unittest.main()
