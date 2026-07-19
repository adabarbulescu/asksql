from __future__ import annotations

import base64
import json
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any, Iterator

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from asksql.adapters import adapter_for
from asksql.connections import ConnectionStore, ConnectionStoreError, normalize_database_url
from asksql.demo import create_demo_db
from asksql.export import format_result
from asksql.llm import check_model
from asksql.models import ConnectionProfile, ExecutionStatus, MutationResult, QueryExecution, QueryResult, TableSchema
from asksql.safety import is_read_only, is_write
from asksql.secrets import set_secret
from asksql.service import QueryService
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, MAX_LIMIT, inspect
from asksql.studio.jobs import ExecutionManager
from asksql.studio.writes import WriteIntentError, WriteIntentManager
from asksql.workspace import WorkspaceStore

DEFAULT_MODEL = "ollama:qwen2.5-coder:7b"


class GenerateRequest(BaseModel):
    connection: str
    question: str = Field(min_length=1, max_length=10_000)
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=200)
    tables: list[str] | None = Field(default=None, max_length=200)


class ExecuteRequest(BaseModel):
    connection: str
    sql: str = Field(min_length=1, max_length=100_000)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    timeout: float = Field(default=DEFAULT_TIMEOUT, gt=0, le=3600)
    history_id: str | None = Field(default=None, max_length=64)
    question: str | None = Field(default=None, max_length=10_000)
    model: str | None = Field(default=None, max_length=200)
    source: str = Field(default="manual", pattern="^(manual|ai)$")


class ConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=4096)


class ConnectionTestRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class ModelCheckRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class PinRequest(BaseModel):
    pinned: bool


class ExportRequest(BaseModel):
    connection: str
    sql: str = Field(min_length=1, max_length=100_000)
    format: str = Field(pattern="^(csv|json|markdown)$")
    limit: int = Field(default=MAX_LIMIT, ge=1, le=MAX_LIMIT)
    timeout: float = Field(default=DEFAULT_TIMEOUT, gt=0, le=3600)


class WriteReviewRequest(BaseModel):
    connection: str
    sql: str = Field(min_length=1, max_length=100_000)


class WriteCommitRequest(WriteReviewRequest):
    token: str = Field(min_length=20, max_length=200)
    timeout: float = Field(default=DEFAULT_TIMEOUT, gt=0, le=3600)


class ExplainRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=100_000)


class SecretRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=10_000)


def create_app(
    *,
    store: ConnectionStore | None = None,
    workspace: WorkspaceStore | None = None,
    jobs: ExecutionManager | None = None,
    writes: WriteIntentManager | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    connection_store = store or ConnectionStore()
    workspace_store = workspace or WorkspaceStore()
    execution_manager = jobs or ExecutionManager()
    write_intents = writes or WriteIntentManager()
    assets = static_dir or Path(__file__).with_name("static")
    app = FastAPI(title="AskSQL Studio", version="0.3.0", docs_url=None, redoc_url=None)
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

    @app.post("/api/connections/test")
    def test_connection(request: ConnectionTestRequest) -> dict[str, object]:
        url, table_count = _validate_database(request.url)
        return {"valid": True, "url": url, "tables": table_count}

    @app.post("/api/connections", status_code=201)
    def add_connection(request: ConnectionRequest) -> dict[str, str]:
        url, _ = _validate_database(request.url)
        try:
            profile = connection_store.add(request.name, url)
        except ConnectionStoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _profile_payload(profile)

    @app.post("/api/connections/demo")
    def add_demo_connection() -> dict[str, str]:
        try:
            profile = connection_store.get("demo")
            inspect(profile.url)
            return _profile_payload(profile)
        except ConnectionStoreError:
            pass
        except Exception:
            connection_store.remove("demo")
        demo_path = connection_store.path.parent / "demo.db"
        profile = connection_store.add("demo", create_demo_db(demo_path))
        return _profile_payload(profile)

    @app.put("/api/connections/{name}")
    def update_connection(name: Annotated[str, ApiPath(min_length=1)], request: ConnectionRequest) -> dict[str, str]:
        url, _ = _validate_database(request.url)
        try:
            profile = connection_store.update(name, request.name, url)
        except ConnectionStoreError as exc:
            status = 404 if str(exc).startswith("unknown connection") else 409
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _profile_payload(profile)

    @app.delete("/api/connections/{name}", status_code=204)
    def remove_connection(name: Annotated[str, ApiPath(min_length=1)]) -> Response:
        try:
            connection_store.remove(name)
        except ConnectionStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/connections/{name}/schema")
    def connection_schema(name: Annotated[str, ApiPath(min_length=1)]) -> dict[str, Any]:
        profile = _profile(connection_store, name)
        try:
            tables = adapter_for(profile.url).inspect_details().tables
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

    @app.get("/api/connections/{name}/schema/details")
    def connection_schema_details(name: Annotated[str, ApiPath(min_length=1)]) -> dict[str, Any]:
        profile = _profile(connection_store, name)
        try:
            details = adapter_for(profile.url).inspect_details()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not inspect schema details: {exc}") from exc
        return {
            "connection": profile.name,
            "tables": [_table_payload(table) for table in details.tables.values()],
            "views": [
                {"name": item.name, "kind": item.kind, "table": item.table, "sql": item.sql} for item in details.views
            ],
            "triggers": [
                {"name": item.name, "kind": item.kind, "table": item.table, "sql": item.sql}
                for item in details.triggers
            ],
        }

    @app.post("/api/connections/{name}/explain")
    def explain(name: Annotated[str, ApiPath(min_length=1)], request: ExplainRequest) -> dict[str, object]:
        profile = _profile(connection_store, name)
        adapter = adapter_for(profile.url)
        if not is_read_only(request.sql, adapter.dialect):
            raise HTTPException(status_code=400, detail="Only read-only SQL can be explained")
        try:
            plan = adapter.explain(request.sql)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not explain query: {exc}") from exc
        return {"columns": plan.columns, "rows": plan.rows}

    @app.post("/api/query/generate")
    def generate(request: GenerateRequest) -> dict[str, str]:
        profile = _profile(connection_store, request.connection)
        try:
            generated = QueryService(profile.url, request.model).generate(request.question, request.tables)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SQL generation failed: {exc}") from exc
        history = workspace_store.create_generated(
            request.connection, generated.question, generated.sql, generated.model
        )
        return {
            "question": generated.question,
            "sql": generated.sql,
            "model": generated.model,
            "historyId": history.id,
        }

    @app.post("/api/query/generate-stream")
    def generate_stream(request: GenerateRequest) -> StreamingResponse:
        profile = _profile(connection_store, request.connection)

        def events() -> Iterator[str]:
            yield json.dumps({"event": "started", "model": request.model}) + "\n"
            try:
                generated = QueryService(profile.url, request.model).generate(request.question, request.tables)
                history = workspace_store.create_generated(
                    request.connection, generated.question, generated.sql, generated.model
                )
                yield (
                    json.dumps(
                        {
                            "event": "completed",
                            "question": generated.question,
                            "sql": generated.sql,
                            "model": generated.model,
                            "historyId": history.id,
                        }
                    )
                    + "\n"
                )
            except Exception as exc:
                yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"

        return StreamingResponse(events(), media_type="application/x-ndjson")

    @app.post("/api/models/check")
    def model_check(request: ModelCheckRequest) -> dict[str, object]:
        ready, detail = check_model(request.model)
        return {"model": request.model, "ready": ready, "detail": detail}

    @app.put("/api/settings/openai", status_code=204)
    def save_openai_settings(request: SecretRequest) -> Response:
        try:
            set_secret("OPENAI_API_KEY", request.api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/query/execute")
    def execute(request: ExecuteRequest) -> dict[str, Any]:
        profile = _profile(connection_store, request.connection)
        history_id = request.history_id
        if history_id is None:
            history_id = workspace_store.create(
                request.connection,
                request.sql,
                source=request.source,
                question=request.question,
                model=request.model,
            ).id
        execution = QueryService(profile.url).execute(
            request.sql,
            limit=request.limit,
            timeout=request.timeout,
            allow_write=False,
        )
        payload = _execution_payload(execution, history_id)
        try:
            workspace_store.complete(history_id, execution)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return payload

    @app.post("/api/query/jobs", status_code=202)
    def start_execution(request: ExecuteRequest) -> dict[str, str]:
        profile = _profile(connection_store, request.connection)
        history_id = request.history_id
        if history_id is None:
            history_id = workspace_store.create(
                request.connection,
                request.sql,
                source=request.source,
                question=request.question,
                model=request.model,
            ).id

        def record_completion(execution: QueryExecution) -> None:
            workspace_store.complete(history_id, execution)

        job = execution_manager.start(
            QueryService(profile.url),
            request.sql,
            history_id,
            limit=request.limit,
            timeout=request.timeout,
            completed=record_completion,
        )
        return {"jobId": job.id, "historyId": history_id, "state": job.state}

    @app.get("/api/query/jobs/{identifier}")
    def execution_job(identifier: Annotated[str, ApiPath(min_length=1)]) -> dict[str, Any]:
        try:
            job = execution_manager.get(identifier)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload: dict[str, Any] = {"jobId": job.id, "historyId": job.history_id, "state": job.state}
        if job.execution is not None:
            payload["execution"] = _execution_payload(job.execution, job.history_id)
        return payload

    @app.delete("/api/query/jobs/{identifier}", status_code=202)
    def cancel_execution(identifier: Annotated[str, ApiPath(min_length=1)]) -> dict[str, str]:
        try:
            job = execution_manager.cancel(identifier)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"jobId": job.id, "state": "cancelling"}

    @app.post("/api/query/export")
    def export_query(request: ExportRequest) -> Response:
        profile = _profile(connection_store, request.connection)
        execution = QueryService(profile.url).execute(request.sql, limit=request.limit, timeout=request.timeout)
        if execution.status != ExecutionStatus.SUCCEEDED or not isinstance(execution.result, QueryResult):
            raise HTTPException(status_code=400, detail=execution.error or "Query could not be exported")
        content = format_result(execution.result, request.format)
        media_types = {"csv": "text/csv", "json": "application/json", "markdown": "text/markdown"}
        return Response(
            content,
            media_type=media_types[request.format],
            headers={"Content-Disposition": f'attachment; filename="asksql-results.{request.format}"'},
        )

    @app.post("/api/write/review")
    def review_write(request: WriteReviewRequest) -> dict[str, str]:
        profile = _profile(connection_store, request.connection)
        if not is_write(request.sql, adapter_for(profile.url).dialect):
            workspace_store.audit_write(
                request.connection, request.sql, "refused", error="Only one supported write statement can be reviewed"
            )
            raise HTTPException(status_code=400, detail="Only one supported write statement can be reviewed")
        intent = write_intents.issue(request.connection, request.sql)
        workspace_store.audit_write(request.connection, request.sql, "reviewed", token_id=intent.sql_hash)
        return {
            "token": intent.token,
            "expiresAt": intent.expires_at,
            "statement": request.sql.lstrip().split(None, 1)[0].upper(),
        }

    @app.post("/api/write/commit", status_code=202)
    def commit_write(request: WriteCommitRequest) -> dict[str, str]:
        profile = _profile(connection_store, request.connection)
        try:
            intent = write_intents.consume(request.token, request.connection, request.sql)
        except WriteIntentError as exc:
            workspace_store.audit_write(request.connection, request.sql, "refused", error=str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        history_id = workspace_store.create(request.connection, request.sql, source="manual").id
        audit_id = workspace_store.audit_write(request.connection, request.sql, "executing", token_id=intent.sql_hash)

        def completed(execution: QueryExecution) -> None:
            workspace_store.complete(history_id, execution)
            workspace_store.complete_write_audit(audit_id, execution)

        job = execution_manager.start(
            QueryService(profile.url),
            request.sql,
            history_id,
            limit=DEFAULT_LIMIT,
            timeout=request.timeout,
            allow_write=True,
            completed=completed,
        )
        return {"jobId": job.id, "historyId": history_id, "state": job.state}

    @app.get("/api/history")
    def history(
        connection: Annotated[str | None, Query(max_length=100)] = None,
        search: Annotated[str | None, Query(max_length=500)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, list[dict[str, object]]]:
        entries = workspace_store.entries(connection_name=connection, search=search, limit=limit)
        return {"history": [entry.payload() for entry in entries]}

    @app.patch("/api/history/{identifier}/pin")
    def pin_history(identifier: Annotated[str, ApiPath(min_length=1)], request: PinRequest) -> dict[str, object]:
        try:
            return workspace_store.set_pinned(identifier, request.pinned).payload()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/history/{identifier}", status_code=204)
    def delete_history(identifier: Annotated[str, ApiPath(min_length=1)]) -> Response:
        try:
            workspace_store.delete(identifier)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.delete("/api/history", status_code=204)
    def clear_history(connection: Annotated[str | None, Query(max_length=100)] = None) -> Response:
        workspace_store.clear(connection)
        return Response(status_code=204)

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


def _validate_database(value: str) -> tuple[str, int]:
    url = value.strip()
    if "://" not in url:
        url = f"sqlite://{url}"
    try:
        normalized = normalize_database_url(url)
        table_count = adapter_for(normalized).validate()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not open database: {exc}") from exc
    return normalized, table_count


def _profile_payload(profile: ConnectionProfile) -> dict[str, str]:
    return {"name": profile.name, "url": profile.url}


def _execution_payload(execution: QueryExecution, history_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sql": execution.sql,
        "status": execution.status.value,
        "durationMs": round(execution.duration_ms, 3),
        "error": execution.error,
        "historyId": history_id,
    }
    if execution.status != ExecutionStatus.SUCCEEDED:
        return payload
    if isinstance(execution.result, MutationResult):
        payload["mutation"] = {
            "affectedRows": execution.result.affected_rows,
            "lastInsertId": execution.result.last_insert_id,
        }
        return payload
    assert isinstance(execution.result, QueryResult)
    payload["result"] = {
        "columns": execution.result.columns,
        "rows": [[_json_value(value) for value in row] for row in execution.result.rows],
        "truncated": execution.result.truncated,
        "limit": execution.result.limit,
    }
    return payload


def _table_payload(table: TableSchema) -> dict[str, object]:
    return {
        "name": table.name,
        "rowCount": table.row_count,
        "columns": [
            {"name": column.name, "type": column.type, "primaryKey": column.primary_key} for column in table.columns
        ],
        "foreignKeys": [
            {
                "column": key.column,
                "referencedTable": key.referenced_table,
                "referencedColumn": key.referenced_column,
            }
            for key in table.foreign_keys
        ],
        "indexes": [{"name": index.name, "columns": index.columns, "unique": index.unique} for index in table.indexes],
    }


def _json_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"type": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
