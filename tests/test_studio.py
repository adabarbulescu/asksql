import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asksql.cli import main
from asksql.connections import ConnectionStore
from asksql.models import AutoFixAttempt, ExecutionStatus, QueryExecution, QueryResult
from asksql.studio import create_app
from asksql.workspace import WorkspaceStore
from tests.api_client import DirectClient


class StudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        database = root / "studio.db"
        self.database = database
        with sqlite3.connect(database) as connection:
            connection.execute("create table projects(id integer primary key, name text)")
            connection.execute("insert into projects(name) values ('AskSQL Studio')")
            connection.execute("create unique index projects_name on projects(name)")
            connection.execute("create view project_names as select name from projects")
            connection.execute(
                "create trigger projects_trim after insert on projects "
                "begin update projects set name = trim(name) where id = new.id; end"
            )
        self.store = ConnectionStore(root / "connections.json")
        self.store.add("local", f"sqlite://{database}")
        self.workspace = WorkspaceStore(root / "workspace.db")
        self.app = create_app(store=self.store, workspace=self.workspace, static_dir=root / "missing-static")
        self.client = DirectClient(self.app)

    def test_lists_connections_and_structured_schema(self) -> None:
        connections = self.client.get("/api/connections")
        schema = self.client.get("/api/connections/local/schema")

        self.assertEqual(connections.status_code, 200)
        self.assertEqual(connections.json()["connections"][0]["name"], "local")
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(schema.json()["tables"][0]["name"], "projects")
        self.assertTrue(schema.json()["tables"][0]["columns"][0]["primaryKey"])

    def test_schema_intelligence_and_query_plan(self) -> None:
        details = self.client.get("/api/connections/local/schema/details")
        plan = self.client.post(
            "/api/connections/local/explain", json={"sql": "select * from projects where name = 'AskSQL Studio'"}
        )

        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()["tables"][0]["rowCount"], 1)
        self.assertEqual(details.json()["tables"][0]["indexes"][0]["name"], "projects_name")
        self.assertEqual(details.json()["views"][0]["name"], "project_names")
        self.assertEqual(details.json()["triggers"][0]["name"], "projects_trim")
        self.assertEqual(plan.status_code, 200)
        self.assertIn("INDEX", plan.json()["rows"][0][3].upper())

    def test_connection_lifecycle_and_validation(self) -> None:
        database = Path(self.directory.name) / "studio.db"

        tested = self.client.post("/api/connections/test", json={"url": str(database)})
        added = self.client.post("/api/connections", json={"name": "second", "url": str(database)})
        updated = self.client.put("/api/connections/second", json={"name": "renamed", "url": f"sqlite://{database}"})
        removed = self.client.delete("/api/connections/renamed")

        self.assertEqual(tested.json()["tables"], 1)
        self.assertEqual(added.status_code, 201)
        self.assertEqual(updated.json()["name"], "renamed")
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(database.stat().st_size == 0)
        self.assertEqual(self.client.get("/api/connections/renamed/schema").status_code, 404)

    def test_connection_rejects_missing_or_invalid_database(self) -> None:
        missing = self.client.post(
            "/api/connections", json={"name": "missing", "url": str(Path(self.directory.name) / "missing.db")}
        )
        invalid_path = Path(self.directory.name) / "invalid.db"
        invalid_path.write_text("not sqlite", encoding="utf-8")
        invalid = self.client.post("/api/connections/test", json={"url": str(invalid_path)})

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(invalid.status_code, 400)

    def test_adds_demo_once(self) -> None:
        first = self.client.post("/api/connections/demo")
        second = self.client.post("/api/connections/demo")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["name"], "demo")
        self.assertEqual(first.json()["url"], f"sqlite://{Path(self.directory.name) / 'demo.db'}")

    def test_checks_model_without_exposing_provider_secrets(self) -> None:
        with patch("asksql.studio.server.check_model", return_value=(True, "ready")) as check:
            response = self.client.post("/api/models/check", json={"model": "ollama:qwen"})

        self.assertEqual(response.json(), {"model": "ollama:qwen", "ready": True, "detail": "ready"})
        check.assert_called_once_with("ollama:qwen")

    def test_reports_first_run_setup_status(self) -> None:
        route = next(route for route in self.app.routes if getattr(route, "path", "") == "/api/setup")
        payload = route.endpoint(model="ollama:test")

        self.assertTrue(payload["ready"])
        self.assertEqual(payload["connections"], 1)
        self.assertEqual(payload["model"], "ollama:test")
        self.assertFalse(payload["modelChecked"])

    def test_reports_redacted_support_diagnostics(self) -> None:
        route = next(route for route in self.app.routes if getattr(route, "path", "") == "/api/diagnostics")
        payload = route.endpoint(model="ollama:test")

        self.assertEqual(payload["connections"][0]["name"], "local")
        self.assertEqual(payload["connections"][0]["target"], "studio.db")
        self.assertNotIn(str(Path(self.directory.name)), str(payload))

    def test_stores_openai_key_without_returning_it(self) -> None:
        with patch("asksql.studio.server.set_secret") as save_secret:
            response = self.client.put("/api/settings/openai", json={"api_key": "private-key"})

        self.assertEqual(response.status_code, 204)
        self.assertNotIn("private-key", response.text)
        save_secret.assert_called_once_with("OPENAI_API_KEY", "private-key")

    def test_executes_read_only_query(self) -> None:
        response = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": "select name from projects"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "succeeded")
        self.assertEqual(response.json()["result"]["rows"], [["AskSQL Studio"]])

    def test_executes_query_with_auto_fix(self) -> None:
        with patch("asksql.studio.server.QueryService.execute_with_repair") as mock_repair:
            mock_repair.return_value = QueryExecution(
                "select name from projects",
                QueryResult(["name"], [("AskSQL Studio",)], False, 200),
                12.5,
                ExecutionStatus.SUCCEEDED,
                None,
                attempts=[
                    AutoFixAttempt(1, "select name from proj", "no such table: proj", ExecutionStatus.FAILED, 5.0),
                    AutoFixAttempt(2, "select name from projects", None, ExecutionStatus.SUCCEEDED, 7.5),
                ],
            )
            response = self.client.post(
                "/api/query/execute",
                json={
                    "connection": "local",
                    "sql": "select name from proj",
                    "question": "show project names",
                    "auto_fix": True,
                    "retries": 2,
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(len(data["attempts"]), 2)
        self.assertEqual(data["attempts"][0]["status"], "failed")
        self.assertEqual(data["attempts"][1]["status"], "succeeded")

    def test_generates_sql_through_existing_query_service(self) -> None:
        with patch("asksql.studio.server.QueryService.generate") as generate:
            generate.return_value.question = "show projects"
            generate.return_value.sql = "select * from projects"
            generate.return_value.model = "ollama:test"
            response = self.client.post(
                "/api/query/generate",
                json={"connection": "local", "question": "show projects", "model": "ollama:test"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sql"], "select * from projects")
        self.assertTrue(response.json()["historyId"])

    def test_refuses_writes_even_when_called_directly(self) -> None:
        response = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": "delete from projects"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "refused")
        with sqlite3.connect(Path(self.directory.name) / "studio.db") as connection:
            self.assertEqual(connection.execute("select count(*) from projects").fetchone(), (1,))

    def test_history_search_pin_restore_and_delete(self) -> None:
        executed = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": "select name from projects", "source": "manual"},
        ).json()
        identifier = executed["historyId"]

        found = self.client.get("/api/history", params={"search": "projects"}).json()["history"]
        pinned = self.client.patch(f"/api/history/{identifier}/pin", json={"pinned": True}).json()
        deleted = self.client.delete(f"/api/history/{identifier}")

        self.assertEqual(found[0]["id"], identifier)
        self.assertEqual(found[0]["status"], "succeeded")
        self.assertTrue(pinned["pinned"])
        self.assertEqual(deleted.status_code, 204)

    def test_persistent_query_document_api(self) -> None:
        created = self.client.post(
            "/api/workspace/documents",
            json={"connection": "local", "title": "Revenue analysis", "selected_tables": ["projects"]},
        )
        identifier = created.json()["id"]
        updated = self.client.patch(
            f"/api/workspace/documents/{identifier}",
            json={
                "question": "show projects",
                "generated_sql": "select * from projects",
                "edited_sql": "select name from projects",
                "lifecycle_state": "generated",
            },
        )
        workspace = self.client.patch(
            "/api/workspace", json={"active_connection": "local", "active_document_id": identifier}
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(updated.json()["edited_sql"], "select name from projects")
        self.assertEqual(workspace.json()["activeDocumentId"], identifier)
        self.assertEqual(self.client.get("/api/workspace").json()["documents"][0]["title"], "Revenue analysis")

    def test_async_execution_updates_query_document_lifecycle(self) -> None:
        document = self.client.post(
            "/api/workspace/documents", json={"connection": "local", "title": "Projects"}
        ).json()
        started = self.client.post(
            "/api/query/jobs",
            json={
                "connection": "local",
                "sql": "select name from projects",
                "document_id": document["id"],
            },
        ).json()

        import time

        job = self.client.get(f"/api/query/jobs/{started['jobId']}").json()
        for _ in range(100):
            if job["state"] == "completed":
                break
            time.sleep(0.01)
            job = self.client.get(f"/api/query/jobs/{started['jobId']}").json()
        restored = self.client.get("/api/workspace").json()["documents"][0]

        self.assertEqual(restored["lifecycle_state"], "completed")
        self.assertEqual(restored["execution_status"], "succeeded")
        self.assertEqual(restored["result_reference"], started["historyId"])

    def test_saved_query_library_api(self) -> None:
        document = self.client.post(
            "/api/workspace/documents", json={"connection": "local", "title": "Projects"}
        ).json()
        created = self.client.post(
            "/api/saved-queries",
            json={
                "name": "Project names",
                "description": "Reusable project lookup",
                "connection_hint": "local",
                "natural_language_question": "show project names",
                "sql": "select name from projects",
                "schema_context": ["projects"],
                "tags": ["Lookup", "projects"],
                "folder": "Operations",
                "favorite": True,
                "source_document_id": document["id"],
            },
        )
        identifier = created.json()["id"]
        found = self.client.get("/api/saved-queries", params={"search": "lookup", "tag": "lookup"}).json()
        updated = self.client.patch(f"/api/saved-queries/{identifier}", json={"favorite": False}).json()
        duplicated = self.client.post(f"/api/saved-queries/{identifier}/duplicate", json={}).json()
        deleted = self.client.delete(f"/api/saved-queries/{identifier}")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(found["savedQueries"][0]["id"], identifier)
        self.assertIn("Operations", found["folders"])
        self.assertFalse(updated["favorite"])
        self.assertEqual(duplicated["name"], "Project names copy")
        self.assertEqual(deleted.status_code, 204)

    def test_semantic_model_crud_compile_generate_and_execute(self) -> None:
        payload = {
            "name": "Projects business model",
            "description": "Canonical project metrics",
            "connection_hint": "local",
            "entities": [{"name": "projects", "source_table": "projects", "primary_key": "id", "description": ""}],
            "metrics": [
                {
                    "name": "projects_count",
                    "label": "Projects count",
                    "description": "Number of projects",
                    "entity": "projects",
                    "aggregation": "count_distinct",
                    "expression": "id",
                    "filters": [],
                    "format": "integer",
                }
            ],
            "dimensions": [
                {
                    "name": "project",
                    "label": "Project",
                    "description": "Project name",
                    "entity": "projects",
                    "expression": "name",
                    "data_type": "text",
                    "time_granularities": [],
                }
            ],
            "relationships": [],
        }
        created = self.client.post("/api/semantic-models", json=payload)
        identifier = created.json()["id"]
        compiled = self.client.post(
            f"/api/semantic-models/{identifier}/compile",
            json={"connection": "local", "metrics": ["projects_count"], "dimensions": [{"name": "project"}]},
        )
        generated = self.client.post(
            "/api/query/generate",
            json={
                "connection": "local",
                "question": "Show projects count by project",
                "model": "ollama:not-needed",
                "semantic_model_id": identifier,
            },
        )
        executed = self.client.post(
            "/api/query/execute",
            json={
                "connection": "local",
                "sql": generated.json()["sql"],
                "semantic_model_id": identifier,
                "semantic_plan": generated.json()["plan"],
            },
        )

        self.assertEqual(created.status_code, 201)
        self.assertIn('count(distinct t0."id")', compiled.json()["sql"])
        self.assertEqual(generated.json()["generationMode"], "semantic")
        self.assertEqual(executed.json()["status"], "succeeded")
        self.assertEqual(executed.json()["result"]["rows"], [["AskSQL Studio", 1]])
        self.assertEqual(
            len(self.client.get("/api/semantic-models", params={"connection": "local"}).json()["semanticModels"]), 1
        )

        payload["description"] = "Updated definitions"
        updated = self.client.put(f"/api/semantic-models/{identifier}", json=payload)
        self.assertEqual(updated.json()["description"], "Updated definitions")
        self.assertEqual(self.client.delete(f"/api/semantic-models/{identifier}").status_code, 204)

    def test_semantic_model_rejects_unknown_physical_columns(self) -> None:
        response = self.client.post(
            "/api/semantic-models",
            json={
                "name": "Invalid",
                "connection_hint": "local",
                "entities": [{"name": "projects", "source_table": "projects", "primary_key": "id", "description": ""}],
                "metrics": [
                    {
                        "name": "revenue",
                        "label": "Revenue",
                        "description": "",
                        "entity": "projects",
                        "aggregation": "sum",
                        "expression": "missing_column",
                        "filters": [],
                        "format": "number",
                    }
                ],
                "dimensions": [],
                "relationships": [],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown column", response.json()["detail"])

    def test_analysis_workflow_runs_reports_exports_and_drills_down(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "create table z_orders(id integer primary key, amount real, status text, created_at text, country text)"
            )
            connection.executemany(
                "insert into z_orders(amount, status, created_at, country) values (?, ?, ?, ?)",
                [
                    (100, "completed", "2026-07-05", "Germany"),
                    (50, "completed", "2026-07-15", "France"),
                    (70, "completed", "2026-08-05", "Germany"),
                    (70, "completed", "2026-08-15", "France"),
                ],
            )
        model = self.client.post(
            "/api/semantic-models",
            json={
                "name": "Commerce",
                "connection_hint": "local",
                "entities": [{"name": "orders", "source_table": "z_orders", "primary_key": "id", "description": ""}],
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
        ).json()
        template = self.client.get("/api/analysis-templates", params={"semantic_model_id": model["id"]}).json()[
            "templates"
        ][0]
        definition = self.client.post(
            "/api/analysis-definitions/from-template",
            json={"semantic_model_id": model["id"], "template": "revenue_investigation"},
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
                },
            },
        ).json()

        import time

        run = started
        for _ in range(200):
            run = self.client.get(f"/api/analysis-runs/{started['id']}").json()
            if run["state"] not in {"planning", "running"}:
                break
            time.sleep(0.01)

        self.assertTrue(template["available"])
        self.assertGreaterEqual(template["estimated_queries"], 5)
        self.assertEqual(run["state"], "completed")
        self.assertIn("decreased by 6.7%", run["report"]["headline"])
        self.assertTrue(run["charts"])
        self.assertTrue(run["evidence"])

        pdf = self.client.get(f"/api/analysis-runs/{run['id']}/export", params={"format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.text.startswith("%PDF-1.4"))

        driver = next(item for item in run["findings"] if item.get("follow_up_analysis"))
        follow_up = self.client.post(f"/api/analysis-runs/{run['id']}/follow-up", json={"finding_id": driver["id"]})
        self.assertEqual(follow_up.status_code, 202)
        self.assertEqual(follow_up.json()["parent_run_id"], run["id"])
        for _ in range(200):
            follow_up_run = self.client.get(f"/api/analysis-runs/{follow_up.json()['id']}").json()
            if follow_up_run["state"] not in {"planning", "running"}:
                break
            time.sleep(0.01)
        self.assertEqual(follow_up_run["state"], "completed")

    def test_parameterized_saved_query_validates_binds_exports_and_hides_sensitive_values(self) -> None:
        document = self.client.post(
            "/api/workspace/documents", json={"connection": "local", "title": "Parameterized"}
        ).json()
        saved = self.client.post(
            "/api/saved-queries",
            json={
                "name": "Project by name",
                "connection_hint": "local",
                "sql": "select name from projects where name = :name and :secret = :secret",
                "source_document_id": document["id"],
                "parameters": [
                    {"name": "name", "data_type": "text", "required": True, "description": "Project name"},
                    {"name": "secret", "data_type": "text", "required": True, "sensitive": True},
                ],
            },
        ).json()
        executed = self.client.post(
            "/api/query/execute",
            json={
                "connection": "local",
                "sql": saved["sql"],
                "saved_query_id": saved["id"],
                "parameter_values": {"name": "AskSQL Studio", "secret": "runtime-only"},
            },
        )
        exported = self.client.post(
            "/api/query/export",
            json={
                "connection": "local",
                "sql": saved["sql"],
                "format": "json",
                "saved_query_id": saved["id"],
                "parameter_values": {"name": "AskSQL Studio", "secret": "runtime-only"},
            },
        )
        missing = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": saved["sql"], "saved_query_id": saved["id"]},
        )
        persisted = self.client.patch(
            f"/api/workspace/documents/{document['id']}",
            json={
                "saved_query_id": saved["id"],
                "parameter_values": {"name": "AskSQL Studio", "secret": "must-not-persist"},
            },
        ).json()

        self.assertEqual(executed.json()["result"]["rows"], [["AskSQL Studio"]])
        self.assertIn("AskSQL Studio", exported.text)
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(persisted["parameter_values"], {"name": "AskSQL Studio"})

    def test_unknown_connection_is_not_found(self) -> None:
        response = self.client.get("/api/connections/missing/schema")

        self.assertEqual(response.status_code, 404)

    def test_cli_ui_delegates_to_studio_server(self) -> None:
        with patch("asksql.cli.run_studio", return_value=0) as studio:
            exit_code = main(["--model", "ollama:test", "ui", "--port", "7444", "--no-open"])

        self.assertEqual(exit_code, 0)
        studio.assert_called_once_with(model="ollama:test", port=7444, open_browser=False)

    def test_packaged_studio_shell_is_served(self) -> None:
        client = DirectClient(create_app(store=self.store, workspace=self.workspace))

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AskSQL Studio", response.text)


if __name__ == "__main__":
    unittest.main()
