from __future__ import annotations

import unittest

from asksql.models import Column, ForeignKey, IndexSchema, TableSchema
from asksql.semantic import model_from_payload, validate_model
from asksql.semantic_bootstrap import infer_semantic_draft, semantic_readiness


def commerce_schema() -> list[TableSchema]:
    return [
        TableSchema(
            "customers",
            [
                Column("id", "INTEGER", True),
                Column("name", "TEXT", False),
                Column("email", "TEXT", False),
                Column("region", "VARCHAR(50)", False),
            ],
            [],
        ),
        TableSchema(
            "orders",
            [
                Column("id", "INTEGER", True),
                Column("customer_id", "INTEGER", False),
                Column("total_amount", "NUMERIC(12,2)", False),
                Column("status", "TEXT", False),
                Column("created_at", "TIMESTAMP", False),
                Column("internal_notes", "TEXT", False),
            ],
            [ForeignKey("customer_id", "customers", "id")],
        ),
    ]


class SemanticBootstrapTest(unittest.TestCase):
    def test_infers_reviewable_model_from_metadata_only(self) -> None:
        draft = infer_semantic_draft(commerce_schema(), connection_hint="local", name="Commerce draft")

        self.assertEqual(draft.state, "draft")
        self.assertTrue(draft.payload()["requires_review"])
        self.assertEqual(draft.model["name"], "Commerce draft")
        self.assertEqual(
            {item["name"] for item in draft.model["entities"]},  # type: ignore[union-attr]
            {"customers", "orders"},
        )
        metrics = {item["name"]: item for item in draft.model["metrics"]}  # type: ignore[union-attr]
        self.assertEqual(metrics["total_amount"]["aggregation"], "sum")
        self.assertEqual(metrics["orders_count"]["aggregation"], "count")
        dimensions = {item["expression"]: item for item in draft.model["dimensions"]}  # type: ignore[union-attr]
        self.assertEqual(dimensions["created_at"]["time_granularities"], ["day", "week", "month", "quarter", "year"])
        self.assertIn("status", dimensions)
        self.assertIn("region", dimensions)
        self.assertNotIn("email", dimensions)
        self.assertNotIn("internal_notes", dimensions)

        relationship = draft.model["relationships"][0]  # type: ignore[index]
        self.assertEqual(relationship["from_entity"], "orders")
        self.assertEqual(relationship["to_entity"], "customers")
        self.assertEqual(relationship["cardinality"], "many_to_one")
        self.assertTrue(any(item.confidence == "high" and item.kind == "relationship" for item in draft.suggestions))

    def test_draft_is_accepted_by_existing_semantic_contract(self) -> None:
        schema = commerce_schema()
        draft = infer_semantic_draft(schema, connection_hint="local")
        model = model_from_payload(draft.model, identifier="draft")

        validate_model(model, {table.name: {column.name for column in table.columns} for table in schema})

    def test_uses_unique_index_then_conventional_or_first_column_as_proposed_key(self) -> None:
        tables = [
            TableSchema(
                "accounts",
                [Column("account_code", "TEXT", False), Column("name", "TEXT", False)],
                [],
                [IndexSchema("accounts_code", ["account_code"], True)],
            ),
            TableSchema("profiles", [Column("id", "INTEGER", False), Column("name", "TEXT", False)], []),
            TableSchema("settings", [Column("key", "TEXT", False), Column("value", "TEXT", False)], []),
        ]

        draft = infer_semantic_draft(tables, connection_hint="local")
        entities = {item["source_table"]: item for item in draft.model["entities"]}  # type: ignore[union-attr]

        self.assertEqual(entities["accounts"]["primary_key"], "account_code")
        self.assertEqual(entities["profiles"]["primary_key"], "id")
        self.assertEqual(entities["settings"]["primary_key"], "key")
        self.assertEqual(len(draft.warnings), 3)

    def test_skips_empty_table_and_dangling_foreign_key(self) -> None:
        draft = infer_semantic_draft(
            [
                TableSchema("empty", [], []),
                TableSchema(
                    "events",
                    [Column("id", "INTEGER", True), Column("owner_id", "INTEGER", False)],
                    [ForeignKey("owner_id", "missing", "id")],
                ),
            ],
            connection_hint="local",
        )

        self.assertEqual([item["name"] for item in draft.model["entities"]], ["events"])  # type: ignore[index]
        self.assertEqual(draft.model["relationships"], [])
        self.assertTrue(any("Skipped empty" in warning for warning in draft.warnings))
        self.assertTrue(any("referenced table missing" in warning for warning in draft.warnings))

    def test_does_not_propose_arbitrary_numeric_columns_as_measures(self) -> None:
        draft = infer_semantic_draft(
            [
                TableSchema(
                    "inventory",
                    [
                        Column("id", "INTEGER", True),
                        Column("year", "INTEGER", False),
                        Column("checksum", "INTEGER", False),
                    ],
                    [],
                )
            ],
            connection_hint="local",
        )

        self.assertEqual(draft.model["metrics"], [])

    def test_readiness_exposes_workflows_and_read_only_query_specs(self) -> None:
        schema = commerce_schema()
        draft = infer_semantic_draft(schema, connection_hint="local")
        report = semantic_readiness(draft.model, schema, freshness_days=30)

        self.assertTrue(report.ready)
        workflows = {item.workflow: item for item in report.workflows}
        self.assertTrue(workflows["metric_change_investigation"].eligible)
        self.assertFalse(workflows["revenue_investigation"].eligible)
        self.assertEqual(workflows["revenue_investigation"].missing, ("Define a revenue-like metric.",))
        kinds = {item.kind for item in report.validation_queries}
        self.assertEqual(kinds, {"null", "duplicate", "freshness", "cardinality"})
        self.assertTrue(all(item.sql.casefold().startswith("select") for item in report.validation_queries))
        freshness = next(item for item in report.validation_queries if item.kind == "freshness")
        self.assertEqual(freshness.expectation["days"], 30)
        orphan = next(item for item in report.validation_queries if item.id.startswith("orphan_fk"))
        self.assertIn('left join "customers"', orphan.sql)

    def test_revenue_workflow_becomes_eligible_for_revenue_metric(self) -> None:
        schema = commerce_schema()
        draft = infer_semantic_draft(schema, connection_hint="local")
        amount = next(item for item in draft.model["metrics"] if item["name"] == "total_amount")  # type: ignore[index]
        amount["name"] = "revenue"
        amount["label"] = "Revenue"

        report = semantic_readiness(draft.model, schema)

        revenue = next(item for item in report.workflows if item.workflow == "revenue_investigation")
        self.assertTrue(revenue.eligible)
        self.assertEqual(revenue.compatible_metrics, ("revenue",))

    def test_invalid_physical_reference_fails_preflight_without_queries(self) -> None:
        schema = commerce_schema()
        draft = infer_semantic_draft(schema, connection_hint="local")
        draft.model["metrics"][0]["expression"] = "missing_column"  # type: ignore[index]

        report = semantic_readiness(draft.model, schema)

        self.assertFalse(report.ready)
        self.assertEqual(report.checks[0].code, "schema_valid")
        self.assertEqual(report.checks[0].status, "failed")
        self.assertEqual(report.validation_queries, ())
        self.assertTrue(all(not item.eligible for item in report.workflows))

    def test_disconnected_entities_are_reported(self) -> None:
        schema = commerce_schema() + [
            TableSchema("products", [Column("id", "INTEGER", True), Column("name", "TEXT", False)], [])
        ]
        draft = infer_semantic_draft(schema, connection_hint="local")

        report = semantic_readiness(draft.model, schema)

        check = next(item for item in report.checks if item.code == "disconnected_entities")
        self.assertEqual(check.status, "warning")
        self.assertIn("products", check.message)

    def test_missing_metric_and_time_dimension_block_metric_change_workflow(self) -> None:
        schema = [TableSchema("settings", [Column("id", "INTEGER", True), Column("name", "TEXT", False)], [])]
        draft = infer_semantic_draft(schema, connection_hint="local")

        report = semantic_readiness(draft.model, schema)

        workflow = next(item for item in report.workflows if item.workflow == "metric_change_investigation")
        self.assertFalse(report.ready)
        self.assertFalse(workflow.eligible)
        self.assertEqual(len(workflow.missing), 2)

    def test_rejects_invalid_freshness_window(self) -> None:
        draft = infer_semantic_draft(commerce_schema(), connection_hint="local")
        with self.assertRaisesRegex(ValueError, "positive"):
            semantic_readiness(draft.model, commerce_schema(), freshness_days=0)

    def test_quotes_schema_identifiers_in_validation_queries(self) -> None:
        schema = [
            TableSchema(
                "order",
                [
                    Column("item_id", "INTEGER", True),
                    Column("total", "REAL", False),
                    Column("created_at", "DATE", False),
                ],
                [],
            )
        ]
        draft = infer_semantic_draft(schema, connection_hint="local")

        report = semantic_readiness(draft.model, schema)

        self.assertTrue(any('"order"' in item.sql for item in report.validation_queries))
        self.assertTrue(any('"item_id"' in item.sql for item in report.validation_queries))


if __name__ == "__main__":
    unittest.main()
