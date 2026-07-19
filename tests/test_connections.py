import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from asksql.cli import main, resolve_db_url
from asksql.connections import ConnectionStore, ConnectionStoreError


class ConnectionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "config"
        self.database = Path(self.directory.name) / "app.db"
        with sqlite3.connect(self.database) as conn:
            conn.execute("create table items(id integer primary key, name text)")
        self.url = f"sqlite://{self.database}"
        self.environment = patch.dict(os.environ, {"ASKSQL_CONFIG_DIR": str(self.config)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_add_list_get_and_remove_profile(self) -> None:
        store = ConnectionStore()

        profile = store.add("local", self.url)

        self.assertEqual(profile.name, "local")
        self.assertEqual(profile.url, f"sqlite://{self.database.resolve()}")
        self.assertEqual(store.list(), [profile])
        self.assertEqual(store.get("local"), profile)
        self.assertEqual(store.remove("local"), profile)
        self.assertEqual(store.list(), [])

    def test_store_is_private_and_versioned(self) -> None:
        store = ConnectionStore()
        store.add("local", self.url)

        payload = json.loads(store.path.read_text())

        self.assertEqual(payload["version"], 1)
        self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_rejects_duplicate_invalid_and_missing_connections(self) -> None:
        store = ConnectionStore()
        store.add("local", self.url)

        with self.assertRaises(ConnectionStoreError):
            store.add("local", self.url)
        with self.assertRaises(ConnectionStoreError):
            store.add("not valid", self.url)
        with self.assertRaises(ConnectionStoreError):
            store.add("missing", f"sqlite://{Path(self.directory.name) / 'missing.db'}")
        with self.assertRaises(ConnectionStoreError):
            store.get("unknown")

    def test_cli_manages_and_resolves_named_connection(self) -> None:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["connections", "add", "local", "--url", self.url]), 0)
            self.assertEqual(main(["--yes", "run", "local", "select count(*) from items"]), 0)

        self.assertEqual(resolve_db_url("local"), f"sqlite://{self.database.resolve()}")
        self.assertEqual(main(["--yes", "connections", "remove", "local"]), 0)

    def test_no_argument_launch_uses_picker_selection(self) -> None:
        ConnectionStore().add("local", self.url)

        with patch("asksql.cli.pick_connection", return_value=f"sqlite://{self.database.resolve()}") as picker:
            with patch("asksql.cli.run_tui") as tui:
                exit_code = main([])

        self.assertEqual(exit_code, 0)
        picker.assert_called_once()
        tui.assert_called_once()

    def test_no_argument_launch_explains_empty_store(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout):
            exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("No saved connections", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
