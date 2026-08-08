import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.models import ExecutionStatus
from asksql.semantic import (
    SemanticModelError,
    SemanticQueryPlan,
    compile_query,
    model_from_payload,
    resolve_question,
    validate_model,
)
from asksql.service import QueryService


def orders_model() -> dict[str, object]:
    return {
        "name": "Commerce",
        "description": "Canonical commerce metrics",
        "connection_hint": "local",
        "entities": [
            {"name": "orders", "source_table": "orders", "primary_key": "id", "description": "Orders"},
            {
                "name": "customers",
                "source_table": "customers",
                "primary_key": "id",
                "description": "Customers",
            },
        ],
        "metrics": [
            {
                "name": "revenue",
                "label": "Revenue",
                "description": "Revenue from completed orders",
                "entity": "orders",
                "aggregation": "sum",
                "expression": "total_amount",
                "filters": [{"column": "status", "operator": "eq", "value": "completed"}],
                "format": "currency",
            }
        ],
        "dimensions": [
            {
                "name": "order_date",
                "label": "Order date",
                "description": "Order creation time",
                "entity": "orders",
                "expression": "created_at",
                "data_type": "datetime",
                "time_granularities": ["day", "month", "year"],
            },
            {
                "name": "customer",
                "label": "Customer",
                "description": "Customer name",
                "entity": "customers",
                "expression": "name",
                "data_type": "text",
                "time_granularities": [],
            },
        ],
        "relationships": [
            {
                "name": "orders_to_customers",
                "from_entity": "orders",
                "to_entity": "customers",
                "from_column": "customer_id",
                "to_column": "id",
                "join_type": "left",
                "cardinality": "many_to_one",
            }
        ],
    }


class SemanticLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_from_payload(orders_model(), identifier="commerce")

    def test_validates_against_the_physical_schema(self) -> None:
        schema = {
            "orders": {"id", "customer_id", "total_amount", "status", "created_at"},
            "customers": {"id", "name"},
        }
        validate_model(self.model, schema)
        schema["orders"].remove("total_amount")
        with self.assertRaisesRegex(SemanticModelError, "unknown column for revenue"):
            validate_model(self.model, schema)

    def test_resolves_metric_and_time_grain_without_generating_sql(self) -> None:
        plan = resolve_question(self.model, "Show revenue by month")

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.metrics, ("revenue",))
        self.assertEqual(plan.dimensions, ({"name": "order_date", "granularity": "month"},))

    def test_compiles_sqlite_with_bound_filters_and_time_dimension(self) -> None:
        plan = SemanticQueryPlan("commerce", ("revenue",), ({"name": "order_date", "granularity": "month"},))
        compiled = compile_query(self.model, plan, "sqlite")

        self.assertIn("strftime('%Y-%m', t0.\"created_at\")", compiled.sql)
        self.assertIn('sum(t0."total_amount")', compiled.sql)
        self.assertIn('t0."status" = :semantic_revenue_0', compiled.sql)
        self.assertEqual(compiled.parameters, {"semantic_revenue_0": "completed"})

    def test_compiles_relationship_join_and_postgres_dialect(self) -> None:
        plan = SemanticQueryPlan("commerce", ("revenue",), ({"name": "customer", "granularity": None},))
        compiled = compile_query(self.model, plan, "postgres")

        self.assertIn('left join "customers" as t1', compiled.sql)
        self.assertIn('t0."customer_id" = t1."id"', compiled.sql)
        self.assertIn('group by t1."name"', compiled.sql)

    def test_refuses_a_relationship_path_that_would_fan_out_the_metric_grain(self) -> None:
        payload = orders_model()
        metric = payload["metrics"][0]  # type: ignore[index]
        metric["entity"] = "customers"  # type: ignore[index]
        metric["expression"] = "id"  # type: ignore[index]
        model = model_from_payload(payload, identifier="commerce")
        plan = SemanticQueryPlan("commerce", ("revenue",), ({"name": "order_date", "granularity": "month"},))

        with self.assertRaisesRegex(SemanticModelError, "fan out metric grain"):
            compile_query(model, plan, "postgres")

    def test_refuses_metrics_from_different_entities_without_preaggregation(self) -> None:
        payload = orders_model()
        payload["metrics"].append(  # type: ignore[union-attr]
            {
                "name": "customers",
                "label": "Customers",
                "description": "Customer count",
                "entity": "customers",
                "aggregation": "count_distinct",
                "expression": "id",
                "filters": [],
                "format": "number",
            }
        )
        model = model_from_payload(payload, identifier="commerce")

        with self.assertRaisesRegex(SemanticModelError, "explicit pre-aggregation"):
            compile_query(model, SemanticQueryPlan("commerce", ("revenue", "customers")), "sqlite")

    def test_executes_compiled_sqlite_with_native_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "semantic.db"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "create table orders(id integer primary key, customer_id integer, total_amount real, "
                    "status text, created_at text)"
                )
                connection.executemany(
                    "insert into orders(customer_id, total_amount, status, created_at) values (?, ?, ?, ?)",
                    [(1, 25.0, "completed", "2026-08-01"), (1, 99.0, "pending", "2026-08-02")],
                )
                connection.execute("create table customers(id integer primary key, name text)")
            compiled = compile_query(self.model, SemanticQueryPlan("commerce", ("revenue",)), "sqlite")
            execution = QueryService(f"sqlite://{database}").execute(compiled.sql, parameters=compiled.parameters)

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.result.rows, [(25.0,)])  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
