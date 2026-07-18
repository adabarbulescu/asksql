import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from asksql.cli import main, print_result
from asksql.export import format_result
from asksql.sqlite import QueryResult


class ExportTest(unittest.TestCase):
    def test_formats_csv_json_and_markdown(self) -> None:
        result = QueryResult(["id", "name"], [(1, "Ada"), (2, None)], False, 200)

        self.assertEqual(format_result(result, "csv"), "id,name\r\n1,Ada\r\n2,\r\n")
        self.assertEqual(json.loads(format_result(result, "json")), [{"id": 1, "name": "Ada"}, {"id": 2, "name": None}])
        self.assertEqual(format_result(result, "markdown"), "| id | name |\n| --- | --- |\n| 1 | Ada |\n| 2 |  |\n")

    def test_run_exports_json_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.json"

            exit_code = main(["--yes", "--format", "json", "--output", str(output), "run", "demo select id, name from customers order by id limit 1"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.read_text()), [{"id": 1, "name": "Ada"}])

    def test_stdout_export_preserves_markup_literals(self) -> None:
        stdout = StringIO()
        result = QueryResult(["value"], [("[red]literal[/red]",)], False, 200)

        with redirect_stdout(stdout):
            exit_code = print_result(result, "csv")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "value\r\n[red]literal[/red]\r\n")

    def test_run_export_stdout_is_machine_readable(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["--yes", "--format", "csv", "run", "demo select id from customers order by id limit 1"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("SQL", stderr.getvalue())

    def test_show_schema_uses_stderr_for_structured_export(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with patch("asksql.cli.generate_sql", return_value="select id from customers order by id limit 1"):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["--yes", "--show-schema", "--format", "csv", "demo", "show customers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("Schema", stderr.getvalue())
        self.assertIn("SQL", stderr.getvalue())

    def test_run_honors_limit(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["--yes", "--limit", "1", "--format", "csv", "run", "demo select id from customers order by id"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("Results limited to 1 rows", stderr.getvalue())

    def test_generated_query_honors_limit(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with patch("asksql.cli.generate_sql", return_value="select id from customers order by id"):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["--yes", "--limit", "1", "--format", "csv", "demo", "show customers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("Results limited to 1 rows", stderr.getvalue())

    def test_invalid_limit_exits_before_query(self) -> None:
        for value in ["0", "-1", "10001", "nope"]:
            with self.subTest(value=value):
                with patch("asksql.cli.query_result") as query:
                    with self.assertRaises(SystemExit):
                        main(["--yes", "--limit", value, "run", "demo select id from customers"])
                query.assert_not_called()

    def test_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.csv"
            output.write_text("existing")

            exit_code = main(["--yes", "--format", "csv", "--output", str(output), "run", "demo select id from customers"])

            self.assertEqual(exit_code, 1)
            self.assertEqual(output.read_text(), "existing")

    def test_force_overwrites_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.csv"
            output.write_text("existing")

            exit_code = main(["--yes", "--force", "--format", "csv", "--output", str(output), "run", "demo select id from customers order by id limit 1"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(output.read_text(), "id\n1\n")

    def test_reports_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = print_result(QueryResult(["id"], [(1,)], False, 200), "csv", directory, force=True)

            self.assertEqual(exit_code, 1)

    def test_rejects_output_for_table_format(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--yes", "--output", "ignored.csv", "run", "demo select id from customers"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")

    def test_rejects_force_without_output(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--yes", "--force", "--format", "csv", "run", "demo select id from customers"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
