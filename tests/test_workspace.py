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


if __name__ == "__main__":
    unittest.main()
