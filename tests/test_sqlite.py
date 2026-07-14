import unittest

from asksql.demo import create_demo_db
from asksql.sqlite import inspect


class SqliteTest(unittest.TestCase):
    def test_inspect_demo_schema(self) -> None:
        tables = inspect(create_demo_db())
        self.assertEqual(tables["customers"][0], ("id", "INTEGER", True))
        self.assertIn("orders", tables)


if __name__ == "__main__":
    unittest.main()
