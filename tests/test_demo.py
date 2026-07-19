import tempfile
import unittest
from pathlib import Path

from asksql.demo import create_demo_db
from asksql.sqlite import query, schema


class DemoTest(unittest.TestCase):
    def test_demo_db(self) -> None:
        db_url = create_demo_db()
        self.assertIn("customers(", schema(db_url))
        columns, rows = query(db_url, "select name from customers order by id limit 1")
        self.assertEqual(columns, ["name"])
        self.assertEqual(rows, [("Ada",)])

    def test_demo_can_be_created_at_persistent_private_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.db"

            url = create_demo_db(path)

            self.assertEqual(url, f"sqlite://{path}")
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
