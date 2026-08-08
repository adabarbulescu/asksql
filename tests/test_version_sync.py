from __future__ import annotations

import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


class VersionSyncTest(unittest.TestCase):
    def run_check(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(root / "scripts/check_versions.py"), *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_release_versions_match_pyproject(self) -> None:
        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Release versions are synchronized", result.stdout)

    def test_release_tag_must_match_canonical_version(self) -> None:
        result = self.run_check("--tag", "v0.0.0")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Tag mismatch", result.stderr)

    def test_matching_release_tag_is_accepted(self) -> None:
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        result = self.run_check("--tag", f"v{project['project']['version']}")

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
