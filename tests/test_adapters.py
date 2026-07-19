import tempfile
import unittest
from pathlib import Path

from asksql.adapters import adapter_for
from asksql.adapters.postgres import PostgreSQLAdapter
from asksql.adapters.sqlite import SQLiteAdapter
from asksql.connections import ConnectionStore, ConnectionStoreError, normalize_database_url
from asksql.demo import create_demo_db


class AdapterRegistryTest(unittest.TestCase):
    def test_resolves_sqlite_and_postgresql(self) -> None:
        self.assertIsInstance(adapter_for(create_demo_db()), SQLiteAdapter)
        self.assertIsInstance(adapter_for("postgresql://user:secret@localhost/app"), PostgreSQLAdapter)

    def test_postgresql_profile_is_normalized_without_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ConnectionStore(Path(directory) / "connections.json")
            profile = store.add("warehouse", "postgresql://user:secret@localhost/app")

        self.assertEqual(profile.url, "postgresql://user:secret@localhost/app")
        with self.assertRaises(ConnectionStoreError):
            normalize_database_url("postgresql:///missing-host")

    def test_rejects_unknown_adapter(self) -> None:
        with self.assertRaises(ValueError):
            adapter_for("mysql://localhost/app")


if __name__ == "__main__":
    unittest.main()
