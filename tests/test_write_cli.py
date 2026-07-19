import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.cli import main


class WriteCliTest(unittest.TestCase):
    def setUp(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="asksql-cli-write-", suffix=".db", delete=False) as file:
            self.path = Path(file.name)
        with sqlite3.connect(self.path) as conn:
            conn.execute("create table items(id integer primary key, name text not null)")
        self.database = f"sqlite://{self.path}"

    def test_run_write_requires_explicit_option(self) -> None:
        exit_code = main(["--yes", "run", self.database, "insert into items(name) values ('blocked')"])

        self.assertEqual(exit_code, 2)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("select count(*) from items").fetchone(), (0,))

    def test_run_write_commits_with_double_opt_in(self) -> None:
        exit_code = main(["--yes", "run", "--write", self.database, "insert into items(name) values ('committed')"])

        self.assertEqual(exit_code, 0)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("select name from items").fetchall(), [("committed",)])

    def test_run_write_rejects_structured_output(self) -> None:
        exit_code = main(["--yes", "--format", "json", "run", "--write", self.database, "delete from items"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
