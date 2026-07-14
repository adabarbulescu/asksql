import unittest

from asksql.demo import create_demo_db
from asksql.sqlite import inspect, preview_table, quote_identifier


class SqliteTest(unittest.TestCase):
    def test_inspect_demo_schema(self) -> None:
        tables = inspect(create_demo_db())
        self.assertEqual(tables["customers"][0], ("id", "INTEGER", True))
        self.assertIn("orders", tables)

    def test_preview_table(self) -> None:
        columns, rows = preview_table(create_demo_db(), "customers", 1)
        self.assertEqual(columns, ["id", "name", "email", "created_at"])
        self.assertEqual(rows[0][1], "Ada")

    def test_quote_identifier(self) -> None:
        self.assertEqual(quote_identifier('weird"name'), '"weird""name"')


if __name__ == "__main__":
    unittest.main()
