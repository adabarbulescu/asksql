import io
import unittest
from unittest.mock import patch

from asksql.cli import main


class AutoFixCliTest(unittest.TestCase):
    def test_ask_with_auto_fix_recovers(self) -> None:
        with patch("asksql.service.generate_sql", return_value="select * from invalid_table"):
            with patch("asksql.service.repair_sql", return_value="select id from customers order by id limit 1"):
                code = main(["--yes", "--auto-fix", "ask", "demo", "get first customer"])
        self.assertEqual(code, 0)

    def test_ask_without_auto_fix_fails_on_broken_query(self) -> None:
        with patch("asksql.service.generate_sql", return_value="select * from invalid_table"):
            code = main(["--yes", "ask", "demo", "get first customer"])
        self.assertEqual(code, 1)

    def test_ask_auto_fix_validates_retries_bounds(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--retries", "0", "ask", "demo", "test"])
        with self.assertRaises(SystemExit):
            main(["--retries", "6", "ask", "demo", "test"])

    def test_ask_auto_fix_preserves_clean_csv_stdout(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            with patch("asksql.service.generate_sql", return_value="select * from invalid_table"):
                with patch("asksql.service.repair_sql", return_value="select id from customers order by id limit 1"):
                    code = main(["--yes", "--auto-fix", "--format", "csv", "ask", "demo", "get first customer"])
        self.assertEqual(code, 0)
        output = stdout.getvalue().strip().replace("\r\n", "\n")
        self.assertEqual(output, "id\n1")


if __name__ == "__main__":
    unittest.main()
