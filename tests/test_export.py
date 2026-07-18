import json
import tempfile
import unittest
from pathlib import Path

from asksql.cli import main
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


if __name__ == "__main__":
    unittest.main()
