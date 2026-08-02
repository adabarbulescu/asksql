from __future__ import annotations

import re
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

AGGREGATIONS = {"sum", "count", "count_distinct", "average", "minimum", "maximum"}
CARDINALITIES = {"many_to_one", "one_to_many", "one_to_one"}
JOIN_TYPES = {"left", "inner"}
TIME_GRAINS = {"day", "week", "month", "quarter", "year"}
FILTER_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class SemanticModelError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticEntity:
    name: str
    source_table: str
    primary_key: str
    description: str = ""


@dataclass(frozen=True)
class SemanticFilter:
    column: str
    operator: str
    value: object


@dataclass(frozen=True)
class SemanticMetric:
    name: str
    label: str
    description: str
    entity: str
    aggregation: str
    expression: str
    filters: tuple[SemanticFilter, ...] = ()
    format: str = "number"


@dataclass(frozen=True)
class SemanticDimension:
    name: str
    label: str
    description: str
    entity: str
    expression: str
    data_type: str
    time_granularities: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticRelationship:
    name: str
    from_entity: str
    to_entity: str
    from_column: str
    to_column: str
    join_type: str = "left"
    cardinality: str = "many_to_one"


@dataclass(frozen=True)
class SemanticModel:
    id: str
    name: str
    description: str
    connection_hint: str
    entities: tuple[SemanticEntity, ...]
    metrics: tuple[SemanticMetric, ...]
    dimensions: tuple[SemanticDimension, ...]
    relationships: tuple[SemanticRelationship, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def payload(self) -> dict[str, object]:
        return {
            **asdict(self),
            "entities": [asdict(item) for item in self.entities],
            "metrics": [asdict(item) for item in self.metrics],
            "dimensions": [asdict(item) for item in self.dimensions],
            "relationships": [asdict(item) for item in self.relationships],
        }

    def prompt_context(self) -> str:
        lines = ["Business definitions:"]
        for metric in self.metrics:
            filters = ", ".join(f"{item.column} {item.operator} {item.value!r}" for item in metric.filters)
            suffix = f"; filters: {filters}" if filters else ""
            lines.append(
                f"Metric {metric.label} ({metric.name}) = "
                f"{metric.aggregation}({metric.entity}.{metric.expression}){suffix}. "
                f"{metric.description}"
            )
        for dimension in self.dimensions:
            grains = f"; grains: {', '.join(dimension.time_granularities)}" if dimension.time_granularities else ""
            lines.append(
                f"Dimension {dimension.label} ({dimension.name}) = {dimension.entity}.{dimension.expression}{grains}. "
                f"{dimension.description}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class SemanticQueryPlan:
    model_id: str
    metrics: tuple[str, ...]
    dimensions: tuple[dict[str, str | None], ...] = ()
    filters: tuple[dict[str, object], ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "metrics": list(self.metrics),
            "dimensions": [dict(item) for item in self.dimensions],
            "filters": [dict(item) for item in self.filters],
        }


@dataclass(frozen=True)
class CompiledSemanticQuery:
    sql: str
    parameters: dict[str, object]
    plan: SemanticQueryPlan
    trace: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def payload(self) -> dict[str, object]:
        return {"sql": self.sql, "parameters": self.parameters, "plan": self.plan.payload(), "trace": list(self.trace)}


def model_from_payload(
    payload: Mapping[str, Any], *, identifier: str = "", created_at: str = "", updated_at: str = ""
) -> SemanticModel:
    entities = tuple(_entity(item) for item in _items(payload, "entities"))
    metrics = tuple(_metric(item) for item in _items(payload, "metrics"))
    dimensions = tuple(_dimension(item) for item in _items(payload, "dimensions"))
    relationships = tuple(_relationship(item) for item in _items(payload, "relationships"))
    model = SemanticModel(
        id=identifier,
        name=_required_text(payload, "name", 200),
        description=str(payload.get("description", "")).strip()[:2_000],
        connection_hint=_required_text(payload, "connection_hint", 100),
        entities=entities,
        metrics=metrics,
        dimensions=dimensions,
        relationships=relationships,
        created_at=created_at,
        updated_at=updated_at,
    )
    validate_model(model)
    return model


def validate_model(model: SemanticModel, schema: Mapping[str, set[str]] | None = None) -> None:
    _unique("entities", [item.name for item in model.entities])
    _unique("metrics", [item.name for item in model.metrics])
    _unique("dimensions", [item.name for item in model.dimensions])
    _unique("relationships", [item.name for item in model.relationships])
    entities = {item.name: item for item in model.entities}
    for model_entity in model.entities:
        if schema is not None:
            columns = schema.get(model_entity.source_table)
            if columns is None:
                raise SemanticModelError(
                    f"unknown source table for entity {model_entity.name}: {model_entity.source_table}"
                )
            if model_entity.primary_key not in columns:
                raise SemanticModelError(
                    f"unknown primary key for entity {model_entity.name}: {model_entity.primary_key}"
                )
    for metric_item in model.metrics:
        metric_entity = entities.get(metric_item.entity)
        if metric_entity is None:
            raise SemanticModelError(f"unknown entity for {metric_item.name}: {metric_item.entity}")
        if schema is not None and metric_item.expression not in schema[metric_entity.source_table]:
            raise SemanticModelError(f"unknown column for {metric_item.name}: {metric_item.expression}")
    for dimension_item in model.dimensions:
        dimension_entity = entities.get(dimension_item.entity)
        if dimension_entity is None:
            raise SemanticModelError(f"unknown entity for {dimension_item.name}: {dimension_item.entity}")
        if schema is not None and dimension_item.expression not in schema[dimension_entity.source_table]:
            raise SemanticModelError(f"unknown column for {dimension_item.name}: {dimension_item.expression}")
    for metric in model.metrics:
        if metric.aggregation not in AGGREGATIONS:
            raise SemanticModelError(f"invalid aggregation for {metric.name}: {metric.aggregation}")
        entity = entities[metric.entity]
        for metric_filter in metric.filters:
            if metric_filter.operator not in FILTER_OPERATORS:
                raise SemanticModelError(f"invalid filter operator for {metric.name}: {metric_filter.operator}")
            if schema is not None and metric_filter.column not in schema[entity.source_table]:
                raise SemanticModelError(f"unknown filter column for {metric.name}: {metric_filter.column}")
    for dimension in model.dimensions:
        invalid = set(dimension.time_granularities) - TIME_GRAINS
        if invalid:
            raise SemanticModelError(f"invalid time granularity for {dimension.name}: {sorted(invalid)[0]}")
        if dimension.time_granularities and dimension.data_type not in {"date", "datetime"}:
            raise SemanticModelError(f"time granularities require a date or datetime dimension: {dimension.name}")
    for relationship in model.relationships:
        if relationship.from_entity not in entities or relationship.to_entity not in entities:
            raise SemanticModelError(f"unknown entity in relationship {relationship.name}")
        if relationship.join_type not in JOIN_TYPES or relationship.cardinality not in CARDINALITIES:
            raise SemanticModelError(f"invalid relationship configuration: {relationship.name}")
        if schema is not None:
            left = entities[relationship.from_entity]
            right = entities[relationship.to_entity]
            if relationship.from_column not in schema[left.source_table]:
                raise SemanticModelError(f"unknown relationship column: {relationship.from_column}")
            if relationship.to_column not in schema[right.source_table]:
                raise SemanticModelError(f"unknown relationship column: {relationship.to_column}")


def resolve_question(model: SemanticModel, question: str) -> SemanticQueryPlan | None:
    normalized = _normal(question)
    metrics = tuple(item.name for item in model.metrics if _mentioned(item.name, item.label, normalized))
    if not metrics:
        return None
    dimensions: list[dict[str, str | None]] = []
    for item in model.dimensions:
        if _mentioned(item.name, item.label, normalized):
            grain = next((grain for grain in item.time_granularities if grain in normalized), None)
            dimensions.append({"name": item.name, "granularity": grain})
    requested_grain = next((grain for grain in TIME_GRAINS if grain in normalized), None)
    if requested_grain and not dimensions:
        candidate = next((item for item in model.dimensions if requested_grain in item.time_granularities), None)
        if candidate:
            dimensions.append({"name": candidate.name, "granularity": requested_grain})
    return SemanticQueryPlan(model.id, metrics, tuple(dimensions))


def compile_query(model: SemanticModel, plan: SemanticQueryPlan, dialect: str) -> CompiledSemanticQuery:
    if dialect not in {"sqlite", "postgres"}:
        raise SemanticModelError(f"unsupported semantic dialect: {dialect}")
    metrics = {item.name: item for item in model.metrics}
    dimensions = {item.name: item for item in model.dimensions}
    entities = {item.name: item for item in model.entities}
    selected_metrics = [_lookup(metrics, name, "metric") for name in plan.metrics]
    if not selected_metrics:
        raise SemanticModelError("semantic query requires at least one metric")
    selected_dimensions = [
        (_lookup(dimensions, str(item.get("name")), "dimension"), item.get("granularity")) for item in plan.dimensions
    ]
    root = selected_metrics[0].entity
    required_entities = {item.entity for item in selected_metrics} | {item.entity for item, _ in selected_dimensions}
    joins = _join_paths(model, root, required_entities)
    ordered_entities = [root]
    for _, left, right in joins:
        for name in (left, right):
            if name not in ordered_entities:
                ordered_entities.append(name)
    aliases = {name: f"t{index}" for index, name in enumerate(ordered_entities)}
    select_parts: list[str] = []
    group_parts: list[str] = []
    trace: list[dict[str, str]] = []
    for dimension, raw_grain in selected_dimensions:
        grain = str(raw_grain) if raw_grain else None
        if grain and grain not in dimension.time_granularities:
            raise SemanticModelError(f"granularity {grain} is not available for {dimension.name}")
        expression = _column(aliases[dimension.entity], dimension.expression, dialect)
        if grain:
            expression = _time_expression(expression, grain, dialect)
        select_parts.append(f"{expression} as {_quote(dimension.name, dialect)}")
        group_parts.append(expression)
        trace.append({"kind": "dimension", "name": dimension.name, "sql": expression})
    parameters: dict[str, object] = {}
    where_parts: list[str] = []
    for metric in selected_metrics:
        column = _column(aliases[metric.entity], metric.expression, dialect)
        expression = _aggregate(metric.aggregation, column)
        select_parts.append(f"{expression} as {_quote(metric.name, dialect)}")
        trace.append({"kind": "metric", "name": metric.name, "sql": expression})
        for filter_index, item in enumerate(metric.filters):
            parameter = f"semantic_{metric.name}_{filter_index}"
            where_parts.append(
                _filter_sql(
                    _column(aliases[metric.entity], item.column, dialect), item.operator, parameter, dialect, item.value
                )
            )
            parameters[parameter] = item.value
    root_entity = entities[root]
    selections = ",\n  ".join(select_parts)
    sql = f"select\n  {selections}\nfrom {_table(root_entity.source_table, dialect)} as {aliases[root]}"
    joined = {root}
    for relationship, left_name, right_name in joins:
        target = right_name if left_name in joined else left_name
        source = left_name if left_name in joined else right_name
        target_entity = entities[target]
        if source == relationship.from_entity:
            source_column, target_column = relationship.from_column, relationship.to_column
        else:
            source_column, target_column = relationship.to_column, relationship.from_column
        sql += (
            f"\n{relationship.join_type} join {_table(target_entity.source_table, dialect)} as {aliases[target]}"
            f" on {_column(aliases[source], source_column, dialect)} = "
            f"{_column(aliases[target], target_column, dialect)}"
        )
        joined.add(target)
        trace.append({"kind": "relationship", "name": relationship.name, "sql": f"{source} -> {target}"})
    if where_parts:
        sql += "\nwhere " + "\n  and ".join(where_parts)
    if group_parts:
        sql += "\ngroup by " + ", ".join(group_parts)
        sql += "\norder by " + ", ".join(group_parts)
    return CompiledSemanticQuery(sql, parameters, plan, tuple(trace))


def _entity(payload: Mapping[str, Any]) -> SemanticEntity:
    return SemanticEntity(
        _name(payload, "name"),
        _source_table(payload),
        _name(payload, "primary_key"),
        str(payload.get("description", ""))[:500],
    )


def _metric(payload: Mapping[str, Any]) -> SemanticMetric:
    filters = tuple(
        SemanticFilter(_name(item, "column"), str(item.get("operator", "eq")), item.get("value"))
        for item in _items(payload, "filters")
    )
    return SemanticMetric(
        _name(payload, "name"),
        _required_text(payload, "label", 200),
        str(payload.get("description", ""))[:1_000],
        _name(payload, "entity"),
        str(payload.get("aggregation", "sum")),
        _name(payload, "expression"),
        filters,
        str(payload.get("format", "number"))[:50],
    )


def _dimension(payload: Mapping[str, Any]) -> SemanticDimension:
    grains = tuple(str(item) for item in payload.get("time_granularities", []) if isinstance(item, str))
    return SemanticDimension(
        _name(payload, "name"),
        _required_text(payload, "label", 200),
        str(payload.get("description", ""))[:1_000],
        _name(payload, "entity"),
        _name(payload, "expression"),
        str(payload.get("data_type", "text")),
        grains,
    )


def _relationship(payload: Mapping[str, Any]) -> SemanticRelationship:
    return SemanticRelationship(
        _name(payload, "name"),
        _name(payload, "from_entity"),
        _name(payload, "to_entity"),
        _name(payload, "from_column"),
        _name(payload, "to_column"),
        str(payload.get("join_type", "left")),
        str(payload.get("cardinality", "many_to_one")),
    )


def _items(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise SemanticModelError(f"{key} must be a list of objects")
    return value


def _name(payload: Mapping[str, Any], key: str) -> str:
    value = _required_text(payload, key, 100)
    if not _NAME.fullmatch(value):
        raise SemanticModelError(f"invalid {key}: {value}")
    return value


def _source_table(payload: Mapping[str, Any]) -> str:
    value = _required_text(payload, "source_table", 200)
    if not all(_NAME.fullmatch(part) for part in value.split(".")):
        raise SemanticModelError(f"invalid source_table: {value}")
    return value


def _required_text(payload: Mapping[str, Any], key: str, limit: int) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise SemanticModelError(f"{key} cannot be empty")
    return value[:limit]


def _unique(kind: str, names: Sequence[str]) -> None:
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise SemanticModelError(f"duplicate {kind}: {', '.join(duplicates)}")


def _normal(value: str) -> str:
    return " " + re.sub(r"[^a-z0-9_]+", " ", value.lower()).strip() + " "


def _mentioned(name: str, label: str, normalized: str) -> bool:
    return f" {name.lower()} " in normalized or f" {label.lower()} " in normalized


def _lookup(items: Mapping[str, Any], name: str, kind: str) -> Any:
    try:
        return items[name]
    except KeyError as exc:
        raise SemanticModelError(f"unknown semantic {kind}: {name}") from exc


def _quote(value: str, dialect: str) -> str:
    del dialect
    return '"' + value.replace('"', '""') + '"'


def _table(value: str, dialect: str) -> str:
    return ".".join(_quote(part, dialect) for part in value.split("."))


def _column(alias: str, name: str, dialect: str) -> str:
    return f"{alias}.{_quote(name, dialect)}"


def _aggregate(kind: str, expression: str) -> str:
    names = {"sum": "sum", "count": "count", "average": "avg", "minimum": "min", "maximum": "max"}
    if kind == "count_distinct":
        return f"count(distinct {expression})"
    return f"{names[kind]}({expression})"


def _time_expression(expression: str, grain: str, dialect: str) -> str:
    if dialect == "postgres":
        return f"date_trunc('{grain}', {expression})"
    formats = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m", "quarter": None, "year": "%Y"}
    if grain == "quarter":
        month = f"cast(strftime('%m', {expression}) as integer)"
        return f"printf('%s-Q%d', strftime('%Y', {expression}), (({month} - 1) / 3) + 1)"
    return f"strftime('{formats[grain]}', {expression})"


def _filter_sql(column: str, operator: str, parameter: str, dialect: str, value: object) -> str:
    del dialect
    operators = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f"{column} {operators[operator]} :{parameter}"


def _join_paths(model: SemanticModel, root: str, required: set[str]) -> list[tuple[SemanticRelationship, str, str]]:
    if required == {root}:
        return []
    adjacency: dict[str, list[tuple[SemanticRelationship, str]]] = {}
    for item in model.relationships:
        adjacency.setdefault(item.from_entity, []).append((item, item.to_entity))
        adjacency.setdefault(item.to_entity, []).append((item, item.from_entity))
    result: list[tuple[SemanticRelationship, str, str]] = []
    included = {root}
    for target in sorted(required - {root}):
        queue: deque[tuple[str, list[tuple[SemanticRelationship, str, str]]]] = deque([(root, [])])
        visited = {root}
        path: list[tuple[SemanticRelationship, str, str]] | None = None
        while queue:
            current, current_path = queue.popleft()
            if current == target:
                path = current_path
                break
            for relationship, neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, [*current_path, (relationship, current, neighbor)]))
        if path is None:
            raise SemanticModelError(f"no relationship path from {root} to {target}")
        for edge in path:
            relationship, source, destination = edge
            fanout = (relationship.cardinality == "many_to_one" and source == relationship.to_entity) or (
                relationship.cardinality == "one_to_many" and source == relationship.from_entity
            )
            if fanout:
                raise SemanticModelError(
                    f"relationship {relationship.name} would fan out metric grain from {source} to {destination}"
                )
            if edge not in result:
                result.append(edge)
                included.add(edge[2])
    return result
