import os
import unittest

from asksql.adapters import adapter_for
from asksql.analysis import AnalysisEngine, revenue_investigation_definition
from asksql.models import ExecutionStatus
from asksql.semantic import SemanticQueryPlan, compile_query, model_from_payload
from asksql.service import QueryService


@unittest.skipUnless(os.getenv("ASKSQL_TEST_POSTGRES"), "PostgreSQL integration URL is not configured")
class PostgreSQLIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.url = os.environ["ASKSQL_TEST_POSTGRES"]
        cls.service = QueryService(cls.url)
        cls.service.execute("drop table if exists asksql_integration", allow_write=True)
        cls.service.execute("drop table if exists asksql_analysis_integration", allow_write=True)
        created = cls.service.execute(
            "create table asksql_integration(id serial primary key, name text not null)", allow_write=True
        )
        if created.status != ExecutionStatus.SUCCEEDED:
            raise RuntimeError(created.error)
        cls.service.execute(
            "create table asksql_analysis_integration(id serial primary key, amount numeric not null, "
            "status text not null, created_at date not null, country text not null)",
            allow_write=True,
        )
        cls.service.execute(
            "insert into asksql_analysis_integration(amount, status, created_at, country) values "
            "(100, 'completed', '2026-07-05', 'Germany'), (50, 'completed', '2026-07-15', 'France'), "
            "(70, 'completed', '2026-08-05', 'Germany'), (70, 'completed', '2026-08-15', 'France')",
            allow_write=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.execute("drop table if exists asksql_integration", allow_write=True)
        cls.service.execute("drop table if exists asksql_analysis_integration", allow_write=True)

    def test_schema_read_and_write(self) -> None:
        inserted = self.service.execute("insert into asksql_integration(name) values ('studio')", allow_write=True)
        selected = self.service.execute("select name from asksql_integration order by id")
        details = adapter_for(self.url).inspect_details()

        self.assertEqual(inserted.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(selected.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(selected.result.rows, [("studio",)])
        self.assertIn("asksql_integration", details.tables)

    def test_statement_timeout(self) -> None:
        execution = self.service.execute("select pg_sleep(0.2)", timeout=0.01)

        self.assertEqual(execution.status, ExecutionStatus.TIMED_OUT)

    def test_native_named_parameter_binding(self) -> None:
        execution = QueryService(self.url).execute("select :value::integer as value", parameters={"value": 42})

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.result.rows, [(42,)])  # type: ignore[union-attr]

    def test_semantic_query_uses_postgres_compiler_and_native_binding(self) -> None:
        model = model_from_payload(
            {
                "name": "Integration",
                "connection_hint": "postgres",
                "entities": [
                    {
                        "name": "items",
                        "source_table": "asksql_integration",
                        "primary_key": "id",
                        "description": "",
                    }
                ],
                "metrics": [
                    {
                        "name": "items_count",
                        "label": "Items count",
                        "description": "",
                        "entity": "items",
                        "aggregation": "count_distinct",
                        "expression": "id",
                        "filters": [{"column": "name", "operator": "eq", "value": "studio"}],
                        "format": "integer",
                    }
                ],
                "dimensions": [],
                "relationships": [],
            },
            identifier="integration",
        )
        compiled = compile_query(model, SemanticQueryPlan("integration", ("items_count",)), "postgres")
        execution = self.service.execute(compiled.sql, parameters=compiled.parameters)

        self.assertEqual(execution.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(execution.result.rows, [(1,)])  # type: ignore[union-attr]

    def test_analysis_engine_executes_bound_semantic_plan_on_postgres(self) -> None:
        model = model_from_payload(
            {
                "name": "Commerce",
                "connection_hint": "postgres",
                "entities": [
                    {
                        "name": "orders",
                        "source_table": "asksql_analysis_integration",
                        "primary_key": "id",
                        "description": "",
                    }
                ],
                "metrics": [
                    {
                        "name": "revenue",
                        "label": "Revenue",
                        "description": "",
                        "entity": "orders",
                        "aggregation": "sum",
                        "expression": "amount",
                        "filters": [{"column": "status", "operator": "eq", "value": "completed"}],
                        "format": "currency",
                    }
                ],
                "dimensions": [
                    {
                        "name": "order_date",
                        "label": "Order date",
                        "description": "",
                        "entity": "orders",
                        "expression": "created_at",
                        "data_type": "date",
                        "time_granularities": ["month"],
                    },
                    {
                        "name": "country",
                        "label": "Country",
                        "description": "",
                        "entity": "orders",
                        "expression": "country",
                        "data_type": "text",
                        "time_granularities": [],
                    },
                ],
                "relationships": [],
            },
            identifier="postgres-analysis",
        )
        definition = revenue_investigation_definition(model, identifier="definition")
        result = AnalysisEngine(self.service).execute(
            definition,
            model,
            {
                "current_start": "2026-08-01",
                "current_end": "2026-09-01",
                "previous_start": "2026-07-01",
                "previous_end": "2026-08-01",
            },
        )

        self.assertEqual(result["state"], "completed")
        self.assertIn("decreased by 6.7%", result["report"]["headline"])


if __name__ == "__main__":
    unittest.main()
