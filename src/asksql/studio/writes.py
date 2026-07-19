from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass(frozen=True)
class WriteIntent:
    token: str
    connection: str
    sql_hash: str
    expires_at: str


class WriteIntentError(ValueError):
    pass


class WriteIntentManager:
    def __init__(self, lifetime_seconds: float = 60) -> None:
        self._lifetime = lifetime_seconds
        self._intents: dict[str, tuple[WriteIntent, float]] = {}
        self._lock = Lock()

    def issue(self, connection: str, sql: str) -> WriteIntent:
        token = secrets.token_urlsafe(32)
        intent = WriteIntent(
            token,
            connection,
            _sql_hash(sql),
            (datetime.now(UTC) + timedelta(seconds=self._lifetime)).isoformat(timespec="seconds"),
        )
        with self._lock:
            self._discard_expired()
            self._intents[token] = (intent, time.monotonic() + self._lifetime)
        return intent

    def consume(self, token: str, connection: str, sql: str) -> WriteIntent:
        with self._lock:
            stored = self._intents.pop(token, None)
        if stored is None:
            raise WriteIntentError("write confirmation is unknown, expired, or already used")
        intent, deadline = stored
        if time.monotonic() > deadline:
            raise WriteIntentError("write confirmation has expired")
        if not secrets.compare_digest(intent.connection, connection) or not secrets.compare_digest(
            intent.sql_hash, _sql_hash(sql)
        ):
            raise WriteIntentError("write confirmation does not match this connection and SQL")
        return intent

    def _discard_expired(self) -> None:
        now = time.monotonic()
        expired = [token for token, (_, deadline) in self._intents.items() if deadline < now]
        for token in expired:
            del self._intents[token]


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()
