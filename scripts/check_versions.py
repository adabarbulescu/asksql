#!/usr/bin/env python3
"""Verify that release-facing package versions match pyproject.toml."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_versions(root: Path = ROOT) -> dict[str, str]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    cargo = tomllib.loads((root / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    tauri = json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    web = json.loads((root / "web/package.json").read_text(encoding="utf-8"))
    web_lock = json.loads((root / "web/package-lock.json").read_text(encoding="utf-8"))
    package_version = _python_package_version(root / "src/asksql/__init__.py")
    return {
        "pyproject.toml": pyproject["project"]["version"],
        "src/asksql/__init__.py": package_version,
        "desktop/src-tauri/Cargo.toml": cargo["package"]["version"],
        "desktop/src-tauri/tauri.conf.json": tauri["version"],
        "web/package.json": web["version"],
        "web/package-lock.json": web_lock["version"],
        "web/package-lock.json packages['']": web_lock["packages"][""]["version"],
    }


def _python_package_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ValueError(f"{path} does not define a string __version__")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="also require a release tag matching v<canonical-version>")
    arguments = parser.parse_args(argv)
    versions = release_versions()
    canonical = versions["pyproject.toml"]
    mismatches = {path: version for path, version in versions.items() if version != canonical}
    if mismatches:
        print(f"Version mismatch: pyproject.toml defines {canonical}", file=sys.stderr)
        for path, version in mismatches.items():
            print(f"- {path}: {version}", file=sys.stderr)
        return 1
    if arguments.tag is not None and arguments.tag != f"v{canonical}":
        print(f"Tag mismatch: expected v{canonical}, got {arguments.tag}", file=sys.stderr)
        return 1
    print(f"Release versions are synchronized at {canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
