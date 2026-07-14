import unittest

from asksql.demo import create_demo_db
from asksql.sqlite import query, schema


class DemoTest(unittest.TestCase):
    def test_demo_db(self) -> None:
        db_url = create_demo_db()
        self.assertIn("customers(", schema(db_url))
        columns, rows = query(db_url, "select name from customers order by id limit 1")
        self.assertEqual(columns, ["name"])
        self.assertEqual(rows, [("Ada",)])


if __name__ == "__main__":
    unittest.main()
