from __future__ import annotations

import base64
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from asksql.connections import ConnectionStore, ConnectionStoreError
from asksql.models import ConnectionProfile, ExecutionStatus, MutationResult, QueryResult
from asksql.service import QueryService
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, MAX_LIMIT, inspect

DEFAULT_MODEL = "ollama:qwen2.5-coder:7b"


class GenerateRequest(BaseModel):
    connection: str
    question: str = Field(min_length=1, max_length=10_000)
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)


class ExecuteRequest(BaseModel):
    connection: str
    sql: str = Field(min_length=1, max_length=100_000)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    timeout: float = Field(default=DEFAULT_TIMEOUT, gt=0, le=3600)


def create_app(*, store: ConnectionStore | None = None, static_dir: Path | None = None) -> FastAPI:
    connection_store = store or ConnectionStore()
    assets = static_dir or Path(__file__).with_name("static")
    app = FastAPI(title="AskSQL Studio", version="0.1.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/connections")
    def connections() -> dict[str, list[dict[str, str]]]:
        try:
            profiles = connection_store.profiles()
        except ConnectionStoreError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"connections": [{"name": profile.name, "url": profile.url} for profile in profiles]}

    @app.get("/api/connections/{name}/schema")
    def connection_schema(name: Annotated[str, ApiPath(min_length=1)]) -> dict[str, Any]:
        profile = _profile(connection_store, name)
        try:
            tables = inspect(profile.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not inspect schema: {exc}") from exc
        return {
            "connection": profile.name,
            "tables": [
                {
                    "name": table.name,
                    "columns": [
                        {"name": column.name, "type": column.type, "primaryKey": column.primary_key}
                        for column in table.columns
                    ],
                    "foreignKeys": [
                        {
                            "column": key.column,
                            "referencedTable": key.referenced_table,
                            "referencedColumn": key.referenced_column,
                        }
                        for key in table.foreign_keys
                    ],
                }
                for table in tables.values()
            ],
        }

    @app.post("/api/query/generate")
    def generate(request: GenerateRequest) -> dict[str, str]:
        profile = _profile(connection_store, request.connection)
        try:
            generated = QueryService(profile.url, request.model).generate(request.question)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SQL generation failed: {exc}") from exc
        return {"question": generated.question, "sql": generated.sql, "model": generated.model}

    @app.post("/api/query/execute")
    def execute(request: ExecuteRequest) -> dict[str, Any]:
        profile = _profile(connection_store, request.connection)
        execution = QueryService(profile.url).execute(
            request.sql,
            limit=request.limit,
            timeout=request.timeout,
            allow_write=False,
        )
        payload: dict[str, Any] = {
            "sql": execution.sql,
            "status": execution.status.value,
            "durationMs": round(execution.duration_ms, 3),
            "error": execution.error,
        }
        if execution.status != ExecutionStatus.SUCCEEDED:
            return payload
        if isinstance(execution.result, MutationResult):
            raise HTTPException(status_code=500, detail="Studio write execution is disabled")
        assert isinstance(execution.result, QueryResult)
        payload["result"] = {
            "columns": execution.result.columns,
            "rows": [[_json_value(value) for value in row] for row in execution.result.rows],
            "truncated": execution.result.truncated,
            "limit": execution.result.limit,
        }
        return payload

    if (assets / "index.html").is_file():
        if (assets / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=assets / "assets"), name="studio-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def studio(path: str) -> FileResponse:
            candidate = (assets / path).resolve()
            if path and assets.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(assets / "index.html")

    return app


def run_studio(*, model: str = DEFAULT_MODEL, port: int = 7331, open_browser: bool = True) -> int:
    url = f"http://127.0.0.1:{port}/?model={model}"
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    print(f"AskSQL Studio: {url}")
    print("Press Ctrl+C to stop.")
    try:
        uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    return 0


def _profile(store: ConnectionStore, name: str) -> ConnectionProfile:
    try:
        return store.get(name)
    except ConnectionStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _json_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"type": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
