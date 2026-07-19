from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from typing import Any
from urllib.error import URLError
from urllib.parse import quote

from asksql.sql import clean_sql

SYSTEM = """Write SQLite SQL.
Return only SQL, no markdown.
Use only the provided schema.
Add a small LIMIT when the user does not specify one."""


def generate_sql(model: str, schema: str, question: str) -> str:
    provider, _, name = model.partition(":")
    if provider == "ollama":
        return ollama(name or "qwen2.5-coder", schema, question)
    if provider == "openai":
        return openai(name or "gpt-4.1-mini", schema, question)
    raise ValueError("model must look like ollama:name or openai:name")


def post_json(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def ollama(model: str, schema: str, question: str) -> str:
    base_url = ollama_base_url()
    prompt = f"{SYSTEM}\n\nSchema:\n{schema}\n\nQuestion:\n{question}\n\nSQL:"
    data = post_json(f"{base_url}/api/generate", {"model": model, "prompt": prompt, "stream": False})
    return clean_sql(str(data.get("response", "")))


def ollama_models() -> list[dict[str, object]]:
    data = get_json(f"{ollama_base_url()}/api/tags")
    models = data.get("models", [])
    return list(models) if isinstance(models, list) else []


def ollama_base_url() -> str:
    if os.getenv("OLLAMA_BASE_URL"):
        return os.environ["OLLAMA_BASE_URL"].rstrip("/")
    for url in ["http://localhost:11434", *_wsl_urls()]:
        try:
            post_json(f"{url}/api/show", {"name": "qwen2.5-coder:7b"})
            return url
        except (OSError, URLError, TimeoutError):
            pass
    return "http://localhost:11434"


def _wsl_urls() -> list[str]:
    urls: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as file:
            urls.extend(f"http://{line.split()[1]}:11434" for line in file if line.startswith("nameserver "))
    except OSError:
        pass
    try:
        output = subprocess.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { "
                "$_.InterfaceAlias -like '*WSL*' -or $_.InterfaceAlias -like '*vEthernet*' "
                "} | Select-Object -First 1 -ExpandProperty IPAddress)",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
        if output:
            urls.append(f"http://{output}:11434")
    except (OSError, subprocess.SubprocessError):
        pass
    return urls


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as res:
        return json.loads(res.read().decode())


def check_model(model: str) -> tuple[bool, str]:
    provider, separator, name = model.partition(":")
    if not separator or not name:
        return False, "Model must look like ollama:name or openai:name."
    try:
        if provider == "ollama":
            models = ollama_models()
            names = {str(item.get("name", "")) for item in models}
            if name not in names and f"{name}:latest" not in names:
                return False, f"Ollama is reachable, but {name} is not installed."
            return True, f"Ollama is ready with {name}."
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return False, "OPENAI_API_KEY is not configured in the AskSQL environment."
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            request = urllib.request.Request(
                f"{base_url}/models/{quote(name, safe='')}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(request, timeout=10):
                pass
            return True, f"The OpenAI-compatible endpoint is ready with {name}."
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"Could not reach {provider}: {exc}"
    return False, "Provider must be ollama or openai."


def openai(model: str, schema: str, question: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for openai:* models")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data = post_json(
        f"{base_url}/chat/completions",
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Schema:\n{schema}\n\nQuestion:\n{question}"},
            ],
        },
        {"Authorization": f"Bearer {api_key}"},
    )
    return clean_sql(str(data["choices"][0]["message"]["content"]))
