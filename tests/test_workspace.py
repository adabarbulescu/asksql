import sqlite3
import tempfile
import unittest
from pathlib import Path

from asksql.models import ExecutionStatus, QueryExecution, QueryResult
from asksql.workspace import WorkspaceStore


class WorkspaceStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = WorkspaceStore(Path(self.directory.name) / "workspace.db")

    def test_generated_query_lifecycle_and_private_storage(self) -> None:
        entry = self.store.create_generated("local", "show users", "select * from users", "ollama:qwen")
        execution = QueryExecution(
            entry.sql,
            QueryResult(["id"], [(1,), (2,)], False, 200),
            12.5,
            ExecutionStatus.SUCCEEDED,
            None,
        )

        completed = self.store.complete(entry.id, execution)

        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(completed.row_count, 2)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_search_pin_delete_and_clear(self) -> None:
        first = self.store.create("one", "select * from users", source="manual")
        second = self.store.create("two", "select * from orders", source="manual")

        self.store.set_pinned(first.id, True)

        self.assertEqual(self.store.entries(search="users")[0].id, first.id)
        self.assertEqual(self.store.entries()[0].id, first.id)
        self.store.delete(second.id)
        self.assertEqual(self.store.clear("one"), 1)
        self.assertEqual(self.store.entries(), [])

    def test_persists_multiple_query_documents_and_active_session(self) -> None:
        first = self.store.create_document(
            "one", title="Revenue", question="monthly revenue", selected_tables=["orders"]
        )
        second = self.store.create_document("two", title="Customers")
        self.store.update_document(
            first.id,
            generated_sql="select sum(total) from orders",
            edited_sql="select sum(total) as revenue from orders",
            lifecycle_state="generated",
        )
        self.store.update_workspace(active_connection="one", active_document_id=first.id)

        reopened = WorkspaceStore(self.store.path).workspace()

        self.assertEqual(reopened["activeDocumentId"], first.id)
        self.assertEqual(len(reopened["documents"]), 2)
        self.assertEqual(reopened["documents"][0]["selected_tables"], ["orders"])
        self.assertEqual(reopened["documents"][0]["lifecycle_state"], "generated")
        self.assertEqual(reopened["documents"][1]["id"], second.id)

    def test_recovers_interrupted_running_document_as_cancelled(self) -> None:
        document = self.store.create_document("one")
        self.store.update_document(document.id, lifecycle_state="running")

        reopened = WorkspaceStore(self.store.path).get_document(document.id)

        self.assertEqual(reopened.lifecycle_state, "cancelled")
        self.assertEqual(reopened.execution_status, "cancelled")

    def test_completes_document_with_result_reference(self) -> None:
        document = self.store.create_document("one")
        execution = QueryExecution(
            "select 1",
            QueryResult(["value"], [(1,)], False, 200),
            4.2,
            ExecutionStatus.SUCCEEDED,
            None,
        )

        completed = self.store.complete_document(document.id, execution, "history-1")

        self.assertEqual(completed.lifecycle_state, "completed")
        self.assertEqual(completed.result_reference, "history-1")
        self.assertEqual(completed.row_count, 1)

    def test_backs_up_existing_unversioned_workspace_before_adopting_it(self) -> None:
        path = Path(self.directory.name) / "old-workspace.db"
        with sqlite3.connect(path) as connection:
            connection.execute("create table legacy(id text primary key)")

        WorkspaceStore(path)

        self.assertTrue(path.with_name("old-workspace.db.pre-migration.bak").is_file())

    def test_backs_up_unsupported_workspace_before_refusing_it(self) -> None:
        path = Path(self.directory.name) / "future-workspace.db"
        with sqlite3.connect(path) as connection:
            connection.execute("create table workspace_meta(version integer not null)")
            connection.execute("insert into workspace_meta(version) values (999)")

        with self.assertRaisesRegex(RuntimeError, "Backup created"):
            WorkspaceStore(path)

        self.assertTrue(path.with_name("future-workspace.db.unsupported-v999.bak").is_file())


if __name__ == "__main__":
    unittest.main()
