from __future__ import annotations

import json
import os
import urllib.request


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


def post_json(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> dict[str, object]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def ollama(model: str, schema: str, question: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    prompt = f"{SYSTEM}\n\nSchema:\n{schema}\n\nQuestion:\n{question}\n\nSQL:"
    data = post_json(f"{base_url}/api/generate", {"model": model, "prompt": prompt, "stream": False})
    return str(data.get("response", "")).strip()


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
    return str(data["choices"][0]["message"]["content"]).strip()
