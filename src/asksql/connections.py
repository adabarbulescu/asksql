from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from asksql.models import ConnectionProfile
from asksql.sqlite import db_path

CONFIG_DIR_ENV = "ASKSQL_CONFIG_DIR"
CONFIG_VERSION = 1
PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ConnectionStoreError(ValueError):
    pass


class ConnectionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_directory() / "connections.json"

    def list(self) -> list[ConnectionProfile]:
        return sorted(self._read(), key=lambda profile: profile.name.casefold())

    def get(self, name: str) -> ConnectionProfile:
        profile = next((profile for profile in self._read() if profile.name == name), None)
        if profile is None:
            raise ConnectionStoreError(f"unknown connection: {name}")
        return profile

    def add(self, name: str, url: str) -> ConnectionProfile:
        validate_profile_name(name)
        profile = ConnectionProfile(name, normalize_sqlite_url(url))
        profiles = self._read()
        if any(existing.name == name for existing in profiles):
            raise ConnectionStoreError(f"connection already exists: {name}")
        profiles.append(profile)
        self._write(profiles)
        return profile

    def remove(self, name: str) -> ConnectionProfile:
        profile = self.get(name)
        self._write([existing for existing in self._read() if existing.name != name])
        return profile

    def _read(self) -> list[ConnectionProfile]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectionStoreError(f"could not read connection store: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("version") != CONFIG_VERSION:
            raise ConnectionStoreError("unsupported connection store format")
        records = payload.get("connections")
        if not isinstance(records, list):
            raise ConnectionStoreError("invalid connection store")
        try:
            return [ConnectionProfile(str(record["name"]), str(record["url"])) for record in records]
        except (KeyError, TypeError) as exc:
            raise ConnectionStoreError("invalid connection store") from exc

    def _write(self, profiles: list[ConnectionProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CONFIG_VERSION,
            "connections": [{"name": profile.name, "url": profile.url} for profile in profiles],
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=".connections-", dir=self.path.parent, text=True)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)


def config_directory() -> Path:
    if configured := os.environ.get(CONFIG_DIR_ENV):
        return Path(configured).expanduser()
    if xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg_config).expanduser() / "asksql"
    return Path.home() / ".config" / "asksql"


def validate_profile_name(name: str) -> None:
    if not PROFILE_NAME.fullmatch(name):
        raise ConnectionStoreError("connection name may contain letters, numbers, dots, underscores, and hyphens")


def normalize_sqlite_url(url: str) -> str:
    try:
        path = db_path(url).resolve()
    except ValueError as exc:
        raise ConnectionStoreError("only SQLite connections are supported") from exc
    if not path.is_file():
        raise ConnectionStoreError(f"SQLite database does not exist: {path}")
    return f"sqlite://{path.as_posix()}"
