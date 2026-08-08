from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase

from asksql.models import QueryResult
from asksql.semantic_bootstrap import SemanticReadiness, ValidationQuerySpec
from asksql.semantic_validation import evaluate_validation_queries


class StubAdapter:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def query(self, sql, limit, timeout, cancellation, parameters=None):  # type: ignore[no-untyped-def]
        column, value = self.values[sql]
        return QueryResult([column], [(value,)], False, limit)


class SemanticValidationTests(TestCase):
    def test_error_failure_blocks_readiness_and_retains_evidence(self) -> None:
        spec = ValidationQuerySpec(
            "pk_duplicate.orders",
            "duplicate",
            "Duplicate keys",
            "error",
            "duplicate sql",
            {"operator": "equals", "value": 0, "column": "invalid_count"},
            {"entity": "orders"},
        )
        payload = evaluate_validation_queries(
            StubAdapter({"duplicate sql": ("invalid_count", 2)}),
            SemanticReadiness(True, (), (), (spec,)),
        )
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["validation_results"][0]["status"], "failed")
        self.assertEqual(payload["validation_results"][0]["observed"], 2)
        self.assertEqual(payload["validation_results"][0]["sql"], "duplicate sql")

    def test_stale_warning_is_visible_without_blocking(self) -> None:
        spec = ValidationQuerySpec(
            "freshness.orders_created_at",
            "freshness",
            "Freshness",
            "warning",
            "freshness sql",
            {"operator": "fresh_within_days", "days": 45, "column": "latest_value"},
            {"dimension": "orders_created_at"},
        )
        payload = evaluate_validation_queries(
            StubAdapter({"freshness sql": ("latest_value", "2025-01-01")}),
            SemanticReadiness(True, (), (), (spec,)),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["validation_results"][0]["status"], "warning")

    def test_recent_value_passes(self) -> None:
        spec = ValidationQuerySpec(
            "freshness.orders_created_at",
            "freshness",
            "Freshness",
            "warning",
            "freshness sql",
            {"operator": "fresh_within_days", "days": 45, "column": "latest_value"},
            {},
        )
        payload = evaluate_validation_queries(
            StubAdapter({"freshness sql": ("latest_value", "2026-01-01")}),
            SemanticReadiness(True, (), (), (spec,)),
            now=datetime(2026, 1, 10, tzinfo=UTC),
        )
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["validation_results"][0]["status"], "passed")
