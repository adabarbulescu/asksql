from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import urlparse

from asksql.connections import ConnectionStore, ConnectionStoreError, config_directory
from asksql.setup import DEFAULT_MODEL


def diagnostics(*, store: ConnectionStore | None = None, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    connection_store = store or ConnectionStore()
    connection_error = ""
    try:
        connections = [_connection_summary(profile.name, profile.url) for profile in connection_store.profiles()]
    except ConnectionStoreError as exc:
        connections = []
        connection_error = str(exc)
    return {
        "asksqlVersion": _version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "configDir": str(config_directory()),
        "model": model,
        "connections": connections,
        "connectionError": connection_error,
    }


def _connection_summary(name: str, url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.scheme == "sqlite":
        target = parsed.path.rsplit("/", 1)[-1] or "(file)"
    else:
        target = f"{parsed.hostname or '(host)'}/{parsed.path.strip('/') or '(database)'}"
    return {"name": name, "kind": parsed.scheme, "target": target}


def _version() -> str:
    try:
        return version("asksql")
    except PackageNotFoundError:
        return "unknown"
