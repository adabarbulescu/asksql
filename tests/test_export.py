import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from asksql.cli import main, print_result
from asksql.export import format_result
from asksql.models import QueryResult


class ExportTest(unittest.TestCase):
    def test_formats_csv_json_and_markdown(self) -> None:
        result = QueryResult(["id", "name"], [(1, "Ada"), (2, None)], False, 200)

        self.assertEqual(format_result(result, "csv"), "id,name\r\n1,Ada\r\n2,\r\n")
        self.assertEqual(json.loads(format_result(result, "json")), [{"id": 1, "name": "Ada"}, {"id": 2, "name": None}])
        self.assertEqual(format_result(result, "markdown"), "| id | name |\n| --- | --- |\n| 1 | Ada |\n| 2 |  |\n")

    def test_run_exports_json_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.json"

            exit_code = main(
                [
                    "--yes",
                    "--format",
                    "json",
                    "--output",
                    str(output),
                    "run",
                    "demo",
                    "select id, name from customers order by id limit 1",
                ]
            )

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
            exit_code = main(
                ["--yes", "--format", "csv", "run", "demo", "select id from customers order by id limit 1"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("SQL", stderr.getvalue())

    def test_show_schema_uses_stderr_for_structured_export(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with patch("asksql.service.generate_sql", return_value="select id from customers order by id limit 1"):
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
            exit_code = main(
                ["--yes", "--limit", "1", "--format", "csv", "run", "demo", "select id from customers order by id"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("Result row limit reached: 1", stderr.getvalue())

    def test_generated_query_honors_limit(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with patch("asksql.service.generate_sql", return_value="select id from customers order by id"):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["--yes", "--limit", "1", "--format", "csv", "ask", "demo", "show customers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")
        self.assertIn("Result row limit reached: 1", stderr.getvalue())

    def test_legacy_ask_form_still_works(self) -> None:
        stdout = StringIO()

        with patch("asksql.service.generate_sql", return_value="select id from customers order by id limit 1"):
            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                exit_code = main(["--yes", "--format", "csv", "demo", "show customers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "id\r\n1\r\n")

    def test_invalid_limit_exits_before_query(self) -> None:
        for value in ["0", "-1", "10001", "nope"]:
            with self.subTest(value=value):
                with patch("asksql.service.query_result") as query:
                    with self.assertRaises(SystemExit):
                        main(["--yes", "--limit", value, "run", "demo", "select id from customers"])
                query.assert_not_called()

    def test_invalid_timeout_exits_before_query(self) -> None:
        for value in ["0", "-1", "nan", "inf", "nope"]:
            with self.subTest(value=value):
                with patch("asksql.service.query_result") as query:
                    with self.assertRaises(SystemExit):
                        main(["--yes", "--timeout", value, "run", "demo", "select id from customers"])
                query.assert_not_called()

    def test_run_passes_timeout_to_query(self) -> None:
        with patch("asksql.service.query_result", return_value=QueryResult(["id"], [(1,)], False, 200)) as query:
            exit_code = main(["--yes", "--timeout", "0.5", "run", "demo", "select id from customers"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(query.call_args.args[3], 0.5)

    def test_timeout_exit_code(self) -> None:
        sql = (
            "with recursive nums(n) as (select 1 union all select n + 1 from nums where n < 100000000) "
            "select sum(a.n + b.n) from nums a, nums b"
        )

        exit_code = main(["--yes", "--timeout", "0.001", "run", "demo", sql])

        self.assertEqual(exit_code, 124)

    def test_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.csv"
            output.write_text("existing")

            exit_code = main(
                ["--yes", "--format", "csv", "--output", str(output), "run", "demo", "select id from customers"]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(output.read_text(), "existing")

    def test_force_overwrites_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "customers.csv"
            output.write_text("existing")

            exit_code = main(
                [
                    "--yes",
                    "--force",
                    "--format",
                    "csv",
                    "--output",
                    str(output),
                    "run",
                    "demo",
                    "select id from customers order by id limit 1",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(output.read_text(), "id\n1\n")

    def test_reports_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = print_result(QueryResult(["id"], [(1,)], False, 200), "csv", directory, force=True)

            self.assertEqual(exit_code, 1)

    def test_rejects_output_for_table_format(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--yes", "--output", "ignored.csv", "run", "demo", "select id from customers"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")

    def test_rejects_force_without_output(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--yes", "--force", "--format", "csv", "run", "demo", "select id from customers"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
