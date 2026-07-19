import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from asksql.connections import ConnectionStore
from asksql.studio.server import create_app
from asksql.studio.writes import WriteIntentError, WriteIntentManager
from asksql.workspace import WorkspaceStore


class WriteIntentManagerTest(unittest.TestCase):
    def test_token_is_bound_and_single_use(self) -> None:
        manager = WriteIntentManager()
        intent = manager.issue("local", "delete from items")

        manager.consume(intent.token, "local", "delete from items")

        with self.assertRaises(WriteIntentError):
            manager.consume(intent.token, "local", "delete from items")

    def test_mismatch_consumes_token(self) -> None:
        manager = WriteIntentManager()
        intent = manager.issue("local", "delete from items")

        with self.assertRaises(WriteIntentError):
            manager.consume(intent.token, "other", "delete from items")
        with self.assertRaises(WriteIntentError):
            manager.consume(intent.token, "local", "delete from items")


class StudioWriteApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.database = root / "writes.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute("create table items(id integer primary key, name text)")
            connection.execute("insert into items(name) values ('before')")
        store = ConnectionStore(root / "connections.json")
        store.add("local", f"sqlite://{self.database}")
        self.workspace = WorkspaceStore(root / "workspace.db")
        self.client = TestClient(create_app(store=store, workspace=self.workspace, static_dir=root / "missing"))

    def test_review_then_commit_write(self) -> None:
        sql = "update items set name = 'after' where id = 1"
        review = self.client.post("/api/write/review", json={"connection": "local", "sql": sql})
        committed = self.client.post(
            "/api/write/commit",
            json={"connection": "local", "sql": sql, "token": review.json()["token"]},
        )
        job_id = committed.json()["jobId"]
        for _ in range(100):
            job = self.client.get(f"/api/query/jobs/{job_id}").json()
            if job["state"] == "completed":
                break
            time.sleep(0.01)

        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["statement"], "UPDATE")
        self.assertEqual(job["execution"]["status"], "succeeded")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("select name from items").fetchone(), ("after",))
        self.assertEqual(self.workspace.write_audit_entries()[0]["outcome"], "succeeded")

    def test_token_cannot_authorize_changed_sql(self) -> None:
        sql = "delete from items where id = 1"
        token = self.client.post("/api/write/review", json={"connection": "local", "sql": sql}).json()["token"]

        response = self.client.post(
            "/api/write/commit",
            json={"connection": "local", "sql": "delete from items", "token": token},
        )

        self.assertEqual(response.status_code, 409)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("select count(*) from items").fetchone(), (1,))

    def test_review_rejects_reads_and_multiple_statements(self) -> None:
        read = self.client.post("/api/write/review", json={"connection": "local", "sql": "select * from items"})
        multiple = self.client.post(
            "/api/write/review", json={"connection": "local", "sql": "delete from items; drop table items"}
        )

        self.assertEqual(read.status_code, 400)
        self.assertEqual(multiple.status_code, 400)


if __name__ == "__main__":
    unittest.main()
