from __future__ import annotations

import os

SERVICE = "asksql"


def get_secret(name: str) -> str | None:
    if value := os.getenv(name):
        return value
    try:
        import keyring

        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str) -> None:
    if name not in {"OPENAI_API_KEY"}:
        raise ValueError("unsupported secret")
    try:
        import keyring

        keyring.set_password(SERVICE, name, value)
    except Exception as exc:
        raise RuntimeError(f"Could not store secret in the operating-system keyring: {exc}") from exc
