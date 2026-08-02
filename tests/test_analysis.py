import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.analysis import (
    AnalysisEngine,
    AnalysisError,
    definition_from_payload,
    plan_analysis,
    report_as_html,
    report_as_pdf,
    revenue_investigation_definition,
)
from asksql.models import CancellationToken
from asksql.semantic import model_from_payload
from asksql.service import QueryService


def commerce_model() -> dict[str, object]:
    return {
        "name": "Commerce",
        "description": "",
        "connection_hint": "local",
        "entities": [{"name": "orders", "source_table": "orders", "primary_key": "id", "description": ""}],
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
            },
            {
                "name": "orders",
                "label": "Orders",
                "description": "",
                "entity": "orders",
                "aggregation": "count_distinct",
                "expression": "id",
                "filters": [{"column": "status", "operator": "eq", "value": "completed"}],
                "format": "integer",
            },
        ],
        "dimensions": [
            {
                "name": "order_date",
                "label": "Order date",
                "description": "",
                "entity": "orders",
                "expression": "created_at",
                "data_type": "datetime",
                "time_granularities": ["day", "month", "year"],
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
            {
                "name": "category",
                "label": "Category",
                "description": "",
                "entity": "orders",
                "expression": "category",
                "data_type": "text",
                "time_granularities": [],
            },
        ],
        "relationships": [],
    }


class AnalysisEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "analysis.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "create table orders(id integer primary key, amount real, status text, created_at text, "
                "country text, category text)"
            )
            connection.executemany(
                "insert into orders(amount, status, created_at, country, category) values (?, ?, ?, ?, ?)",
                [
                    (100, "completed", "2026-07-05", "Germany", "Core"),
                    (50, "completed", "2026-07-15", "France", "Core"),
                    (70, "completed", "2026-08-05", "Germany", "Core"),
                    (70, "completed", "2026-08-15", "France", "Growth"),
                    (500, "pending", "2026-08-20", "Germany", "Core"),
                ],
            )
        self.model = model_from_payload(commerce_model(), identifier="commerce")
        self.definition = revenue_investigation_definition(self.model, identifier="definition")
        self.inputs = {
            "current_start": "2026-08-01",
            "current_end": "2026-09-01",
            "previous_start": "2026-07-01",
            "previous_end": "2026-08-01",
        }

    def test_plans_a_bounded_dag_with_bound_period_filters(self) -> None:
        planned = plan_analysis(self.definition, self.model, self.inputs)

        self.assertGreaterEqual(len(planned), 7)
        self.assertLessEqual(len(planned), 30)
        first_filters = planned[0].plan.filters
        self.assertEqual(first_filters[0]["operator"], "gte")
        self.assertEqual(first_filters[0]["value"], "2026-08-01")

    def test_executes_revenue_investigation_and_produces_evidence_findings_and_charts(self) -> None:
        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(
            self.definition, self.model, self.inputs
        )

        self.assertEqual(result["state"], "completed")
        self.assertTrue(all(item["status"] == "succeeded" for item in result["evidence"]))
        self.assertIn("decreased by 6.7%", result["report"]["headline"])
        self.assertTrue(any("Germany" in item["claim"] for item in result["findings"]))
        self.assertTrue(any(item["type"] == "line" for item in result["charts"]))
        self.assertTrue(any(item["type"] == "bar" for item in result["charts"]))

    def test_scope_filter_drives_a_follow_up_analysis(self) -> None:
        scoped = {**self.inputs, "scope_filters": [{"dimension": "country", "value": "Germany"}]}
        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(self.definition, self.model, scoped)

        self.assertEqual(result["state"], "completed")
        self.assertIn("decreased by 30.0%", result["report"]["headline"])

    def test_cancelled_analysis_does_not_execute_queries(self) -> None:
        token = CancellationToken()
        token.cancel()
        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(
            self.definition, self.model, self.inputs, cancellation=token
        )

        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["evidence"], [])

    def test_report_exports_real_html_and_pdf_documents(self) -> None:
        run = {
            "definition_name": "Revenue Investigation",
            "state": "completed",
            "report": {"headline": "Revenue decreased.", "summary": "Germany was the primary driver."},
            "findings": [{"title": "Germany", "claim": "Revenue declined."}],
            "evidence": [{"id": "evidence"}],
        }

        self.assertIn("<!doctype html>", report_as_html(run))
        self.assertTrue(report_as_pdf(run).startswith(b"%PDF-1.4"))

    def test_definition_rejects_dependency_cycles(self) -> None:
        payload = self.definition.payload()
        payload["steps"] = [
            {"id": "a", "type": "period_comparison", "metric": "revenue", "depends_on": ["b"]},
            {"id": "b", "type": "period_comparison", "metric": "revenue", "depends_on": ["a"]},
        ]
        with self.assertRaisesRegex(AnalysisError, "cycle"):
            definition_from_payload(payload)


if __name__ == "__main__":
    unittest.main()
