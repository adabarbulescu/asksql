import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from asksql.cli import main
from asksql.connections import ConnectionStore
from asksql.studio import create_app


class StudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        database = root / "studio.db"
        with sqlite3.connect(database) as connection:
            connection.execute("create table projects(id integer primary key, name text)")
            connection.execute("insert into projects(name) values ('AskSQL Studio')")
        self.store = ConnectionStore(root / "connections.json")
        self.store.add("local", f"sqlite://{database}")
        self.client = TestClient(create_app(store=self.store, static_dir=root / "missing-static"))

    def test_lists_connections_and_structured_schema(self) -> None:
        connections = self.client.get("/api/connections")
        schema = self.client.get("/api/connections/local/schema")

        self.assertEqual(connections.status_code, 200)
        self.assertEqual(connections.json()["connections"][0]["name"], "local")
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(schema.json()["tables"][0]["name"], "projects")
        self.assertTrue(schema.json()["tables"][0]["columns"][0]["primaryKey"])

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

    def test_executes_read_only_query(self) -> None:
        response = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": "select name from projects"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "succeeded")
        self.assertEqual(response.json()["result"]["rows"], [["AskSQL Studio"]])

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

    def test_refuses_writes_even_when_called_directly(self) -> None:
        response = self.client.post(
            "/api/query/execute",
            json={"connection": "local", "sql": "delete from projects"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "refused")
        with sqlite3.connect(Path(self.directory.name) / "studio.db") as connection:
            self.assertEqual(connection.execute("select count(*) from projects").fetchone(), (1,))

    def test_unknown_connection_is_not_found(self) -> None:
        response = self.client.get("/api/connections/missing/schema")

        self.assertEqual(response.status_code, 404)

    def test_cli_ui_delegates_to_studio_server(self) -> None:
        with patch("asksql.cli.run_studio", return_value=0) as studio:
            exit_code = main(["--model", "ollama:test", "ui", "--port", "7444", "--no-open"])

        self.assertEqual(exit_code, 0)
        studio.assert_called_once_with(model="ollama:test", port=7444, open_browser=False)

    def test_packaged_studio_shell_is_served(self) -> None:
        client = TestClient(create_app(store=self.store))

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AskSQL Studio", response.text)


if __name__ == "__main__":
    unittest.main()
