from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

PARAMETER_TYPES = {"text", "integer", "decimal", "boolean", "date", "datetime"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    data_type: str
    required: bool = True
    default_value: object | None = None
    description: str = ""
    sensitive: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ParameterDefinition:
        name = str(payload.get("name", "")).strip()
        data_type = str(payload.get("data_type", "text"))
        if not _NAME.fullmatch(name):
            raise ValueError(f"invalid parameter name: {name or '(empty)'}")
        if data_type not in PARAMETER_TYPES:
            raise ValueError(f"invalid parameter type for {name}: {data_type}")
        default_value = payload.get("default_value")
        if default_value not in (None, ""):
            default_value = _coerce(name, data_type, default_value)
        return cls(
            name,
            data_type,
            bool(payload.get("required", True)),
            default_value,
            str(payload.get("description", ""))[:500],
            bool(payload.get("sensitive", False)),
        )

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "required": self.required,
            "default_value": self.default_value,
            "description": self.description,
            "sensitive": self.sensitive,
        }


def detect_parameters(sql: str) -> list[str]:
    found: list[str] = []
    i = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    while i < len(sql):
        pair = sql[i : i + 2]
        char = sql[i]
        if line_comment:
            if char == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if pair == "*/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if pair == "--":
            line_comment = True
            i += 2
            continue
        if pair == "/*":
            block_comment = True
            i += 2
            continue
        if char in {"'", '"'}:
            quote = char
            i += 1
            continue
        if char == ":" and (i == 0 or sql[i - 1] != ":"):
            match = _NAME.match(sql, i + 1)
            if match:
                name = match.group(0)
                if name not in found:
                    found.append(name)
                i = match.end()
                continue
        i += 1
    return found


def validate_and_bind(sql: str, definitions: list[ParameterDefinition], values: dict[str, object]) -> dict[str, object]:
    placeholders = detect_parameters(sql)
    by_name = {definition.name: definition for definition in definitions}
    missing_definitions = [name for name in placeholders if name not in by_name]
    unused_definitions = [name for name in by_name if name not in placeholders]
    if missing_definitions:
        raise ValueError(f"missing parameter definitions: {', '.join(missing_definitions)}")
    if unused_definitions:
        raise ValueError(f"parameters not present in SQL: {', '.join(unused_definitions)}")
    bound: dict[str, object] = {}
    for name in placeholders:
        definition = by_name[name]
        value = values.get(name, definition.default_value)
        if value in (None, ""):
            if definition.required:
                raise ValueError(f"parameter {name} is required")
            bound[name] = None
            continue
        bound[name] = _coerce(name, definition.data_type, value)
    unknown = sorted(set(values) - set(placeholders))
    if unknown:
        raise ValueError(f"unknown parameter values: {', '.join(unknown)}")
    return bound


def normalize_sql(sql: str, dialect: str) -> str:
    if dialect == "sqlite":
        return sql
    if dialect != "postgres":
        raise ValueError(f"unsupported parameter dialect: {dialect}")
    names = set(detect_parameters(sql))
    if not names:
        return sql
    output: list[str] = []
    i = 0
    quote: str | None = None
    while i < len(sql):
        char = sql[i]
        if quote:
            output.append(char)
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    output.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if char in {"'", '"'}:
            quote = char
            output.append(char)
            i += 1
            continue
        if char == ":" and (i == 0 or sql[i - 1] != ":"):
            match = _NAME.match(sql, i + 1)
            if match and match.group(0) in names:
                output.append(f"%({match.group(0)})s")
                i = match.end()
                continue
        output.append(char)
        i += 1
    return "".join(output)


def _coerce(name: str, data_type: str, value: object) -> object:
    try:
        if data_type == "text":
            return str(value)
        if data_type == "integer":
            if isinstance(value, bool):
                raise ValueError
            return int(str(value))
        if data_type == "decimal":
            return Decimal(str(value))
        if data_type == "boolean":
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
            raise ValueError
        if data_type == "date":
            return date.fromisoformat(str(value))
        if data_type == "datetime":
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"parameter {name} must be {data_type}") from exc
    raise ValueError(f"invalid parameter type for {name}: {data_type}")
