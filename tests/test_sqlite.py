import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.demo import create_demo_db
from asksql.sqlite import DEFAULT_LIMIT, inspect, limited_query, preview_table, query_result, quote_identifier, schema


class SqliteTest(unittest.TestCase):
    def test_inspect_demo_schema(self) -> None:
        tables = inspect(create_demo_db())
        self.assertEqual(tables["customers"].columns[0].name, "id")
        self.assertEqual(tables["customers"].columns[0].type, "INTEGER")
        self.assertTrue(tables["customers"].columns[0].primary_key)
        self.assertIn("orders", tables)

    def test_inspect_demo_foreign_key(self) -> None:
        foreign_key = inspect(create_demo_db())["orders"].foreign_keys[0]

        self.assertEqual(foreign_key.column, "customer_id")
        self.assertEqual(foreign_key.referenced_table, "customers")
        self.assertEqual(foreign_key.referenced_column, "id")

    def test_schema_includes_keys_and_relationships(self) -> None:
        text = schema(create_demo_db())

        self.assertIn("id INTEGER PRIMARY KEY", text)
        self.assertIn("customer_id INTEGER REFERENCES customers(id)", text)

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

    def test_inspect_quotes_unusual_identifiers(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="asksql-test-", suffix=".db", delete=False) as file:
            path = Path(file.name)
        with sqlite3.connect(path) as conn:
            conn.execute('create table "weird""table"(id integer primary key)')

        tables = inspect(f"sqlite://{path}")

        self.assertIn('weird"table', tables)
        self.assertEqual(tables['weird"table'].columns[0].name, "id")

    def test_inspect_preserves_composite_foreign_keys(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="asksql-test-", suffix=".db", delete=False) as file:
            path = Path(file.name)
        with sqlite3.connect(path) as conn:
            conn.executescript(
                """
                create table parent(a integer, b integer, primary key(a, b));
                create table child(x integer, y integer, foreign key(x, y) references parent(a, b));
                """
            )

        foreign_keys = inspect(f"sqlite://{path}")["child"].foreign_keys

        self.assertEqual({(fk.column, fk.referenced_table, fk.referenced_column) for fk in foreign_keys}, {("x", "parent", "a"), ("y", "parent", "b")})


if __name__ == "__main__":
    unittest.main()
