import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from asksql import __version__
from asksql.analysis import metric_change_investigation_definition
from asksql.connections import ConnectionStore
from asksql.studio import create_app
from asksql.workspace import WorkspaceStore
from tests.api_client import DirectClient


def semantic_payload(*, primary_key: str = "id") -> dict[str, object]:
    return {
        "name": "Events model",
        "description": "Reviewed test model",
        "connection_hint": "local",
        "entities": [{"name": "events", "source_table": "events", "primary_key": primary_key, "description": ""}],
        "metrics": [
            {
                "name": "event_value",
                "label": "Event value",
                "description": "",
                "entity": "events",
                "aggregation": "sum",
                "expression": "amount",
                "filters": [],
                "format": "currency",
            }
        ],
        "dimensions": [
            {
                "name": "event_date",
                "label": "Event date",
                "description": "",
                "entity": "events",
                "expression": "created_at",
                "data_type": "datetime",
                "time_granularities": ["month"],
            },
            {
                "name": "category",
                "label": "Category",
                "description": "",
                "entity": "events",
                "expression": "category",
                "data_type": "text",
                "time_granularities": [],
            },
        ],
        "relationships": [],
    }


class StudioSprintApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        database = root / "events.db"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "create table events(id integer primary key, amount real not null, created_at text not null, "
                "category text not null)"
            )
            connection.executemany(
                "insert into events(amount, created_at, category) values (?, ?, ?)",
                [(20, "2026-07-05", "Core"), (30, "2026-08-05", "Core")],
            )
        self.connections = ConnectionStore(root / "connections.json")
        self.connections.add("local", f"sqlite://{database}")
        self.workspace = WorkspaceStore(root / "workspace.db")
        self.app = create_app(
            store=self.connections,
            workspace=self.workspace,
            static_dir=root / "missing-static",
        )
        self.client = DirectClient(self.app)

    def test_uses_package_version_and_proposes_an_unpersisted_reviewable_draft(self) -> None:
        proposal = self.client.post("/api/semantic-models/propose", json={"connection": "local"})

        self.assertEqual(self.app.version, __version__)
        self.assertEqual(proposal.status_code, 200)
        self.assertEqual(proposal.json()["state"], "draft")
        self.assertTrue(proposal.json()["requires_review"])
        self.assertTrue(proposal.json()["model"]["metrics"])
        self.assertEqual(self.workspace.semantic_models("local"), [])

    def test_evaluates_draft_readiness_through_the_agreed_post_contract(self) -> None:
        response = self.client.post("/api/semantic-models/readiness", json=semantic_payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])
        self.assertTrue(response.json()["validation_results"])
        workflow = next(
            item for item in response.json()["workflows"] if item["workflow"] == "metric_change_investigation"
        )
        self.assertEqual(workflow["compatible_metrics"], ["event_value"])

    def test_lists_and_creates_a_configured_generic_analysis_template(self) -> None:
        model = self.client.post("/api/semantic-models", json=semantic_payload()).json()

        templates = self.client.get("/api/analysis-templates", params={"semantic_model_id": model["id"]}).json()[
            "templates"
        ]
        generic = next(item for item in templates if item["id"] == "metric_change_investigation")
        created = self.client.post(
            "/api/analysis-definitions/from-template",
            json={
                "semantic_model_id": model["id"],
                "template": "metric_change_investigation",
                "metric_name": "event_value",
                "time_dimension_name": "event_date",
                "slice_dimension_names": ["category"],
            },
        )

        self.assertTrue(generic["available"])
        self.assertEqual(generic["fields"]["metric_name"]["options"][0]["value"], "event_value")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["template"], "metric_change_investigation")
        self.assertEqual(created.json()["steps"][0]["metric"], "event_value")

    def test_preflight_rejects_duplicate_semantic_keys_before_an_analysis_run(self) -> None:
        model = self.client.post("/api/semantic-models", json=semantic_payload(primary_key="category")).json()
        definition = self.client.post(
            "/api/analysis-definitions/from-template",
            json={
                "semantic_model_id": model["id"],
                "template": "metric_change_investigation",
                "metric_name": "event_value",
                "time_dimension_name": "event_date",
            },
        ).json()

        started = self.client.post(
            "/api/analysis-runs",
            json={
                "definition_id": definition["id"],
                "input_values": {
                    "current_start": "2026-08-01",
                    "current_end": "2026-09-01",
                    "previous_start": "2026-07-01",
                    "previous_end": "2026-08-01",
                    "_trust_checks": [{"status": "passed", "id": "client-spoof"}],
                },
            },
        )

        self.assertEqual(started.status_code, 422)
        self.assertIn("Duplicate primary keys", started.json()["detail"])
        self.assertEqual(self.workspace.analysis_runs(), [])

    def test_preflight_overwrites_client_trust_checks_and_runs_can_be_filtered_by_model(self) -> None:
        analyses = MagicMock()
        app = create_app(
            store=self.connections,
            workspace=self.workspace,
            analyses=analyses,
            static_dir=Path(self.directory.name) / "missing-static",
        )
        client = DirectClient(app)
        first_model = self.workspace.create_semantic_model(semantic_payload())
        second_payload = semantic_payload()
        second_payload["name"] = "Second events model"
        second_model = self.workspace.create_semantic_model(second_payload)
        first_definition = self.workspace.create_analysis_definition(
            metric_change_investigation_definition(
                first_model, metric_name="event_value", time_dimension_name="event_date"
            ).payload()
        )
        second_definition = self.workspace.create_analysis_definition(
            metric_change_investigation_definition(
                second_model, metric_name="event_value", time_dimension_name="event_date"
            ).payload()
        )
        self.workspace.create_analysis_run(second_definition, second_model.payload(), {})

        started = client.post(
            "/api/analysis-runs",
            json={
                "definition_id": first_definition.id,
                "input_values": {
                    "current_start": "2026-08-01",
                    "current_end": "2026-09-01",
                    "previous_start": "2026-07-01",
                    "previous_end": "2026-08-01",
                    "_trust_checks": [{"id": "client-spoof", "status": "passed"}],
                },
            },
        )
        filtered = client.get("/api/analysis-runs", params={"semantic_model_id": first_model.id, "limit": 10}).json()[
            "analysisRuns"
        ]

        self.assertEqual(started.status_code, 202)
        stored_checks = started.json()["input_values"]["_trust_checks"]
        self.assertNotIn("client-spoof", {item["id"] for item in stored_checks})
        self.assertIn("pk_null.events", {item["id"] for item in stored_checks})
        self.assertEqual([item["semantic_model_id"] for item in filtered], [first_model.id])
        analyses.start.assert_called_once()

    def test_demo_provisions_one_curated_model_idempotently(self) -> None:
        first = self.client.post("/api/connections/demo")
        second = self.client.post("/api/connections/demo")
        models = self.workspace.semantic_models("demo")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "AskSQL Demo business model")
        self.assertIn("Curated and reviewed", models[0].description)

    def test_demo_upgrades_a_legacy_managed_database_before_provisioning(self) -> None:
        demo_path = Path(self.directory.name) / "demo.db"
        with sqlite3.connect(demo_path) as connection:
            connection.execute("create table customers(id integer primary key, name text)")
            connection.execute("create table orders(id integer primary key, total real, created_at text)")
        self.connections.add("demo", f"sqlite://{demo_path}")

        response = self.client.post("/api/connections/demo")

        self.assertEqual(response.status_code, 200)
        with sqlite3.connect(demo_path) as connection:
            columns = {row[1] for row in connection.execute("pragma table_info(orders)")}
            self.assertTrue({"status", "channel", "customer_id"} <= columns)
            self.assertEqual(connection.execute("select count(*) from orders").fetchone()[0], 12)
        self.assertEqual(len(self.workspace.semantic_models("demo")), 1)


if __name__ == "__main__":
    unittest.main()
