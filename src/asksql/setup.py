from __future__ import annotations

from typing import Any

from asksql.connections import ConnectionStore, ConnectionStoreError, config_directory
from asksql.llm import check_model

DEFAULT_MODEL = "ollama:qwen2.5-coder:7b"


def setup_status(
    *,
    store: ConnectionStore | None = None,
    model: str = DEFAULT_MODEL,
    check_models: bool = False,
) -> dict[str, Any]:
    connection_store = store or ConnectionStore()
    next_steps: list[str] = []
    connection_error = ""
    try:
        connections = connection_store.profiles()
    except ConnectionStoreError as exc:
        connections = []
        connection_error = str(exc)
        next_steps.append("Fix the connection store or set ASKSQL_CONFIG_DIR to a writable config directory.")

    if not connections and not connection_error:
        next_steps.append(
            "Add a database with `asksql connections add NAME --url sqlite://path/to.db` or use Studio demo data."
        )

    model_ready = False
    model_detail = "not checked"
    if check_models:
        model_ready, model_detail = check_model(model)
    else:
        next_steps.append("Run `asksql setup --check-model` to verify the selected model provider.")

    if check_models and not model_ready:
        if model.startswith("ollama:"):
            next_steps.append("Start Ollama and install the selected model, or switch to an OpenAI-compatible model.")
        elif model.startswith("openai:"):
            next_steps.append("Save an API key in Studio or set OPENAI_API_KEY before using openai:* models.")
        else:
            next_steps.append("Choose a model named like ollama:name or openai:name.")

    return {
        "ready": bool(connections) and (model_ready or not check_models) and not connection_error,
        "configDir": str(config_directory()),
        "connections": len(connections),
        "connectionError": connection_error,
        "model": model,
        "modelChecked": check_models,
        "modelReady": model_ready,
        "modelDetail": model_detail,
        "nextSteps": next_steps,
    }
