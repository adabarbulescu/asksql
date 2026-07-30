import os
import subprocess
import sys
import tempfile
import unittest
from importlib.resources import files
from unittest.mock import patch

from asksql.studio import create_app


class ReleaseSmokeTest(unittest.TestCase):
    def test_installed_cli_runs_demo_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "ASKSQL_CONFIG_DIR": directory}
            result = subprocess.run(
                [sys.executable, "-m", "asksql", "--yes", "run", "demo", "select 1 as ready"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ready", result.stdout)

    def test_packaged_studio_health_and_static_assets_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"ASKSQL_CONFIG_DIR": directory}):
                app = create_app()
        health = next(route for route in app.routes if getattr(route, "path", "") == "/api/health")

        self.assertEqual(health.endpoint(), {"status": "ok"})
        self.assertTrue(files("asksql.studio").joinpath("static/index.html").is_file())


if __name__ == "__main__":
    unittest.main()
