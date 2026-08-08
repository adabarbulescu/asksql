import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.analysis import (
    AnalysisEngine,
    AnalysisError,
    definition_from_payload,
    metric_change_investigation_definition,
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

    def test_investigates_a_non_revenue_metric_without_reserved_report_wording(self) -> None:
        payload = commerce_model()
        payload["metrics"] = [
            {
                "name": "gross_merchandise_value",
                "label": "Gross merchandise value",
                "description": "",
                "entity": "orders",
                "aggregation": "sum",
                "expression": "amount",
                "filters": [{"column": "status", "operator": "eq", "value": "completed"}],
                "format": "currency",
            }
        ]
        model = model_from_payload(payload, identifier="commerce-gmv")
        definition = metric_change_investigation_definition(
            model,
            metric_name="gross_merchandise_value",
            time_dimension_name="order_date",
            slice_dimension_names=["country"],
            identifier="gmv-definition",
        )

        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(definition, model, self.inputs)

        self.assertIn("Gross merchandise value decreased by 6.7%", result["report"]["headline"])
        self.assertNotIn("Revenue", result["report"]["summary"])
        self.assertEqual(definition.steps[0]["id"], "metric_change")
        self.assertTrue(any(chart["title"] == "Gross merchandise value trend" for chart in result["charts"]))

    def test_applies_contribution_top_n_with_deterministic_tie_breaking(self) -> None:
        payload = self.definition.payload()
        for step in payload["steps"]:
            if step["type"] == "dimensional_contribution":
                step["top_n"] = 1
        definition = definition_from_payload(payload, identifier="top-one")

        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(definition, self.model, self.inputs)
        contribution_charts = [chart for chart in result["charts"] if chart["type"] == "bar"]

        self.assertTrue(contribution_charts)
        self.assertTrue(all(len(chart["labels"]) == 1 for chart in contribution_charts))
        labels_by_title = {chart["title"]: chart["labels"] for chart in contribution_charts}
        self.assertEqual(labels_by_title["Revenue contribution by Country"], ["Germany"])
        self.assertEqual(labels_by_title["Revenue contribution by Category"], ["Core"])

    def test_rejects_non_comparable_periods_but_accepts_equal_calendar_months(self) -> None:
        with self.assertRaisesRegex(AnalysisError, "equal durations or matching calendar-month spans"):
            plan_analysis(
                self.definition,
                self.model,
                {**self.inputs, "previous_end": "2026-07-20"},
            )

        planned = plan_analysis(
            self.definition,
            self.model,
            {
                "current_start": "2026-04-01",
                "current_end": "2026-05-01",
                "previous_start": "2026-03-01",
                "previous_end": "2026-04-01",
            },
        )
        self.assertTrue(planned)

    def test_reads_v08_revenue_step_ids_and_keeps_compatibility_template(self) -> None:
        self.assertEqual(self.definition.template, "revenue_investigation")
        self.assertEqual(self.definition.name, "Revenue Investigation")
        payload = self.definition.payload()
        replacements = {"metric_change": "revenue_change", "metric_trend": "revenue_trend"}
        for step in payload["steps"]:
            step["id"] = replacements.get(step["id"], step["id"])
            step["depends_on"] = [replacements.get(item, item) for item in step["depends_on"]]
        legacy = definition_from_payload(payload, identifier="legacy-definition")

        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(legacy, self.model, self.inputs)

        self.assertIn("Revenue decreased by 6.7%", result["report"]["headline"])
        self.assertTrue(any(step["id"] == "revenue_change.current" for step in result["steps"]))

    def test_cancelled_analysis_does_not_execute_queries(self) -> None:
        token = CancellationToken()
        token.cancel()
        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(
            self.definition, self.model, self.inputs, cancellation=token
        )

        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["evidence"], [])

    def test_semantic_trust_warnings_reduce_report_confidence(self) -> None:
        inputs = {
            **self.inputs,
            "_trust_checks": [
                {"status": "passed", "severity": "error"},
                {"status": "warning", "severity": "warning"},
            ],
        }

        result = AnalysisEngine(QueryService(f"sqlite://{self.database}")).execute(self.definition, self.model, inputs)

        self.assertEqual(result["report"]["confidence_basis"]["semantic_trust"], 50)
        self.assertLess(result["report"]["confidence_score"], 100)

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
