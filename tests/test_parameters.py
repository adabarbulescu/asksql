import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.parameters import ParameterDefinition, detect_parameters, normalize_sql, validate_and_bind
from asksql.service import QueryService


class ParameterTest(unittest.TestCase):
    def test_detects_named_placeholders_without_literals_comments_or_casts(self) -> None:
        sql = "select ':ignored', value::text from orders where created_at >= :start and status = :status -- :nope"

        self.assertEqual(detect_parameters(sql), ["start", "status"])
        self.assertIn("%(start)s", normalize_sql(sql, "postgres"))
        self.assertIn("value::text", normalize_sql(sql, "postgres"))

    def test_validates_and_coerces_parameter_types(self) -> None:
        definitions = [
            ParameterDefinition("count", "integer"),
            ParameterDefinition("active", "boolean"),
            ParameterDefinition("start", "date"),
        ]

        bound = validate_and_bind(
            "select :count, :active, :start", definitions, {"count": "3", "active": "true", "start": "2026-08-01"}
        )

        self.assertEqual(bound["count"], 3)
        self.assertIs(bound["active"], True)
        self.assertEqual(str(bound["start"]), "2026-08-01")

    def test_rejects_missing_unknown_and_invalid_values(self) -> None:
        definition = [ParameterDefinition("count", "integer")]
        with self.assertRaisesRegex(ValueError, "required"):
            validate_and_bind("select :count", definition, {})
        with self.assertRaisesRegex(ValueError, "must be integer"):
            validate_and_bind("select :count", definition, {"count": "three"})
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            validate_and_bind("select :count", definition, {"count": 1, "extra": 2})

    def test_sqlite_executes_with_native_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "orders.db"
            with sqlite3.connect(database) as connection:
                connection.execute("create table orders(id integer, status text)")
                connection.executemany("insert into orders values (?, ?)", [(1, "completed"), (2, "pending")])

            execution = QueryService(f"sqlite://{database}").execute(
                "select id from orders where status = :status", parameters={"status": "completed"}
            )

        self.assertEqual(execution.result.rows, [(1,)])  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
