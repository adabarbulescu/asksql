from __future__ import annotations

import inspect
import json as json_module
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.responses import FileResponse, Response


@dataclass
class DirectResponse:
    status_code: int
    payload: Any = None
    text: str = ""

    def json(self) -> Any:
        return self.payload


class DirectClient:
    def __init__(self, app: Any) -> None:
        self.app = app

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> DirectResponse:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> DirectResponse:
        return self._request("POST", path, json=json)

    def put(self, path: str, *, json: dict[str, Any] | None = None) -> DirectResponse:
        return self._request("PUT", path, json=json)

    def patch(self, path: str, *, json: dict[str, Any] | None = None) -> DirectResponse:
        return self._request("PATCH", path, json=json)

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> DirectResponse:
        return self._request("DELETE", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> DirectResponse:
        route = self._route(method, path)
        kwargs = {**route.path_regex.match(path).groupdict(), **(params or {})}  # type: ignore[union-attr]
        signature = inspect.signature(route.endpoint)
        hints = get_type_hints(route.endpoint)
        for name, parameter in signature.parameters.items():
            if name in kwargs:
                continue
            model = _model_type(hints.get(name, parameter.annotation))
            if model:
                kwargs[name] = model(**(json or {}))
        try:
            result = route.endpoint(**kwargs)
        except HTTPException as exc:
            return DirectResponse(exc.status_code, {"detail": exc.detail}, json_module.dumps({"detail": exc.detail}))
        return _response(result, route.status_code or 200)

    def _route(self, method: str, path: str) -> APIRoute:
        for route in self.app.routes:
            if isinstance(route, APIRoute) and method in route.methods and route.path_regex.match(path):
                return route
        raise AssertionError(f"no route for {method} {path}")


def _model_type(annotation: Any) -> type[BaseModel] | None:
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) is not None:
        for item in get_args(annotation):
            model = _model_type(item)
            if model:
                return model
    return None


def _response(result: Any, status_code: int) -> DirectResponse:
    if isinstance(result, FileResponse):
        return DirectResponse(status_code, text=Path(result.path).read_text(encoding="utf-8"))
    if isinstance(result, Response):
        body = result.body.decode("utf-8") if result.body else ""
        return DirectResponse(result.status_code, text=body)
    return DirectResponse(status_code, result, json_module.dumps(result))
