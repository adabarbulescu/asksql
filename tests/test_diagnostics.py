import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from asksql.cli import main
from asksql.connections import ConnectionStore
from asksql.diagnostics import diagnostics


class DiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "config"
        self.database = Path(self.directory.name) / "private.db"
        with sqlite3.connect(self.database) as connection:
            connection.execute("create table items(id integer)")
        self.environment = patch.dict(os.environ, {"ASKSQL_CONFIG_DIR": str(self.config)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_diagnostics_redacts_connection_urls(self) -> None:
        store = ConnectionStore()
        store.add("local", f"sqlite://{self.database}")
        store.add("warehouse", "postgresql://user:secret@example.com/analytics")

        report = diagnostics(store=store, model="ollama:test")

        self.assertEqual(report["connections"][0]["target"], "private.db")
        self.assertEqual(report["connections"][1]["target"], "example.com/analytics")
        self.assertNotIn("secret", str(report))

    def test_cli_prints_diagnostics(self) -> None:
        ConnectionStore().add("local", f"sqlite://{self.database}")
        stdout = StringIO()

        with redirect_stdout(stdout):
            exit_code = main(["diagnostics"])

        self.assertEqual(exit_code, 0)
        self.assertIn("AskSQL diagnostics", stdout.getvalue())
        self.assertNotIn(str(self.database), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
