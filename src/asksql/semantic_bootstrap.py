from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable, Literal, Mapping, Sequence

from asksql.models import Column, TableSchema
from asksql.semantic import (
    SemanticEntity,
    SemanticModel,
    SemanticModelError,
    SemanticRelationship,
    model_from_payload,
    validate_model,
)

Confidence = Literal["high", "medium", "low"]

_NUMERIC_TYPES = (
    "int",
    "numeric",
    "decimal",
    "real",
    "double",
    "float",
    "money",
)
_DATE_TYPES = ("date", "time")
_TEXT_TYPES = ("char", "text", "string", "varchar", "enum", "bool")
_MEASURE_NAMES = (
    "amount",
    "total",
    "revenue",
    "sales",
    "income",
    "price",
    "cost",
    "value",
    "quantity",
    "qty",
    "balance",
    "duration",
)
_CATEGORICAL_NAMES = (
    "status",
    "state",
    "type",
    "category",
    "country",
    "region",
    "segment",
    "channel",
    "source",
    "plan",
    "tier",
    "name",
)
_UNSUITABLE_DIMENSION_NAMES = ("email", "phone", "address", "description", "notes", "body", "json", "token")
_EVENT_TABLE_NAMES = ("order", "sale", "payment", "invoice", "transaction", "event", "session", "subscription")


@dataclass(frozen=True)
class SemanticSuggestion:
    path: str
    kind: str
    label: str
    reason: str
    confidence: Confidence

    def payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticDraft:
    """An unpersisted proposal. Callers must require review before saving it."""

    model: dict[str, object]
    suggestions: tuple[SemanticSuggestion, ...]
    warnings: tuple[str, ...]
    state: str = "draft"

    def payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "requires_review": True,
            "model": self.model,
            "suggestions": [item.payload() for item in self.suggestions],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    status: str
    severity: str
    message: str
    path: str | None = None

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowEligibility:
    workflow: str
    eligible: bool
    missing: tuple[str, ...]
    compatible_metrics: tuple[str, ...] = ()
    compatible_time_dimensions: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationQuerySpec:
    """A read-only query plus a machine-readable expectation; this module never executes it."""

    id: str
    kind: str
    title: str
    severity: str
    sql: str
    expectation: dict[str, object]
    subject: dict[str, str]

    def payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticReadiness:
    ready: bool
    checks: tuple[ReadinessCheck, ...]
    workflows: tuple[WorkflowEligibility, ...]
    validation_queries: tuple[ValidationQuerySpec, ...]

    def payload(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "checks": [item.payload() for item in self.checks],
            "workflows": [item.payload() for item in self.workflows],
            "validation_queries": [item.payload() for item in self.validation_queries],
        }


def infer_semantic_draft(
    tables: Sequence[TableSchema] | Mapping[str, TableSchema],
    *,
    connection_hint: str,
    name: str = "Suggested business model",
) -> SemanticDraft:
    """Infer a conservative semantic model from schema metadata only.

    No rows are accepted or inspected. The result is explicitly a draft and is
    deliberately separate from the persistent semantic-model API.
    """

    ordered = _tables(tables)
    used_names: set[str] = set()
    entity_names: dict[str, str] = {}
    entities: list[dict[str, object]] = []
    metrics: list[dict[str, object]] = []
    dimensions: list[dict[str, object]] = []
    relationships: list[dict[str, object]] = []
    suggestions: list[SemanticSuggestion] = []
    warnings: list[str] = []

    for table in ordered:
        entity_name = _unique_name(_identifier(table.name), used_names)
        entity_names[table.name] = entity_name
        primary_key, key_confidence, key_reason = _primary_key(table)
        if primary_key is None:
            warnings.append(f"Skipped {table.name}: it has no columns")
            continue
        if not any(column.primary_key for column in table.columns):
            warnings.append(f"{table.name} has no declared primary key; review the proposed key {primary_key}")
        entities.append(
            {
                "name": entity_name,
                "source_table": table.name,
                "primary_key": primary_key,
                "description": f"Suggested from table {table.name}",
            }
        )
        suggestions.append(
            SemanticSuggestion(f"entities.{entity_name}", "entity", table.name, key_reason, key_confidence)
        )

    valid_tables = {str(item["source_table"]) for item in entities}
    for table in ordered:
        proposed_entity_name = entity_names.get(table.name)
        if table.name not in valid_tables or proposed_entity_name is None:
            continue
        entity_name = proposed_entity_name
        foreign_key_columns = {item.column for item in table.foreign_keys}
        primary_keys = {column.name for column in table.columns if column.primary_key}
        fact_like = bool(table.foreign_keys) or _contains(table.name, _EVENT_TABLE_NAMES)

        if fact_like:
            count_name = _unique_name(f"{entity_name}_count", used_names)
            primary_key = next((str(item["primary_key"]) for item in entities if item["name"] == entity_name), "")
            metrics.append(_metric(count_name, f"{_label(entity_name)} count", entity_name, "count", primary_key))
            suggestions.append(
                SemanticSuggestion(
                    f"metrics.{count_name}",
                    "metric",
                    f"{_label(entity_name)} count",
                    "Event-like tables support a conservative row-count metric.",
                    "medium",
                )
            )

        for column in table.columns:
            if column.name in primary_keys or column.name in foreign_key_columns:
                continue
            if _is_numeric(column) and _contains(column.name, _MEASURE_NAMES):
                metric_name = _unique_name(_identifier(column.name), used_names)
                metrics.append(_metric(metric_name, _label(column.name), entity_name, "sum", column.name))
                suggestions.append(
                    SemanticSuggestion(
                        f"metrics.{metric_name}",
                        "metric",
                        _label(column.name),
                        f"Numeric column {table.name}.{column.name} has a measure-like name.",
                        "high",
                    )
                )
            if _is_temporal(column):
                dimension_name = _unique_name(_identifier(f"{entity_name}_{column.name}"), used_names)
                dimensions.append(
                    _dimension(
                        dimension_name,
                        _label(column.name),
                        entity_name,
                        column.name,
                        "date" if _normal_type(column.type) == "date" else "datetime",
                        ["day", "week", "month", "quarter", "year"],
                    )
                )
                reason = (
                    f"Column {table.name}.{column.name} has temporal type {column.type}."
                    if any(token in _normal_type(column.type) for token in _DATE_TYPES)
                    else f"Column {table.name}.{column.name} has a conventional temporal name."
                )
                suggestions.append(
                    SemanticSuggestion(f"dimensions.{dimension_name}", "dimension", _label(column.name), reason, "high")
                )
            elif _is_categorical(column):
                dimension_name = _unique_name(_identifier(f"{entity_name}_{column.name}"), used_names)
                dimensions.append(
                    _dimension(dimension_name, _label(column.name), entity_name, column.name, _data_type(column), [])
                )
                suggestions.append(
                    SemanticSuggestion(
                        f"dimensions.{dimension_name}",
                        "dimension",
                        _label(column.name),
                        f"Column {table.name}.{column.name} has a categorical name and compatible type.",
                        "medium",
                    )
                )

        for foreign_key in table.foreign_keys:
            target_entity = entity_names.get(foreign_key.referenced_table)
            if target_entity is None or foreign_key.referenced_table not in valid_tables:
                warnings.append(
                    f"Ignored foreign key {table.name}.{foreign_key.column}: referenced table "
                    f"{foreign_key.referenced_table} is unavailable"
                )
                continue
            relationship_name = _unique_name(f"{entity_name}_to_{target_entity}", used_names)
            relationships.append(
                {
                    "name": relationship_name,
                    "from_entity": entity_name,
                    "to_entity": target_entity,
                    "from_column": foreign_key.column,
                    "to_column": foreign_key.referenced_column,
                    "join_type": "left",
                    "cardinality": "many_to_one",
                }
            )
            suggestions.append(
                SemanticSuggestion(
                    f"relationships.{relationship_name}",
                    "relationship",
                    relationship_name,
                    f"Declared foreign key {table.name}.{foreign_key.column} references "
                    f"{foreign_key.referenced_table}.{foreign_key.referenced_column}.",
                    "high",
                )
            )

    model: dict[str, object] = {
        "name": name,
        "description": "Draft inferred from database schema metadata; review every definition before saving.",
        "connection_hint": connection_hint,
        "entities": entities,
        "metrics": metrics,
        "dimensions": dimensions,
        "relationships": relationships,
    }
    return SemanticDraft(model, tuple(suggestions), tuple(warnings))


def semantic_readiness(
    model_payload: Mapping[str, object],
    tables: Sequence[TableSchema] | Mapping[str, TableSchema],
    *,
    freshness_days: int = 45,
) -> SemanticReadiness:
    """Build structural checks, workflow eligibility, and read-only validation query specs."""

    if freshness_days < 1:
        raise ValueError("freshness_days must be positive")
    ordered = _tables(tables)
    schema = {table.name: {column.name for column in table.columns} for table in ordered}
    checks: list[ReadinessCheck] = []
    try:
        model = model_from_payload(model_payload, identifier="draft")
        validate_model(model, schema)
        checks.append(ReadinessCheck("schema_valid", "passed", "error", "All semantic references exist."))
    except (SemanticModelError, ValueError) as exc:
        checks.append(ReadinessCheck("schema_valid", "failed", "error", str(exc)))
        return SemanticReadiness(False, tuple(checks), _ineligible_workflows(), ())

    if not model.entities:
        checks.append(ReadinessCheck("entities", "failed", "error", "At least one entity is required."))
    if not model.metrics:
        checks.append(ReadinessCheck("metrics", "failed", "error", "At least one reviewed metric is required."))
    else:
        checks.append(ReadinessCheck("metrics", "passed", "error", f"{len(model.metrics)} metric(s) defined."))

    connected = _connected_entities(
        model.entities,
        model.relationships,
        (item.entity for item in model.metrics),
    )
    disconnected = sorted(entity.name for entity in model.entities if entity.name not in connected)
    if len(model.entities) > 1 and disconnected:
        checks.append(
            ReadinessCheck(
                "disconnected_entities",
                "warning",
                "warning",
                f"Disconnected entities: {', '.join(disconnected)}.",
                "relationships",
            )
        )
    else:
        checks.append(ReadinessCheck("entity_graph", "passed", "warning", "Entity graph is connected."))

    time_dimensions = tuple(item.name for item in model.dimensions if "month" in item.time_granularities)
    metric_names = tuple(item.name for item in model.metrics)
    revenue_metrics = tuple(
        item.name for item in model.metrics if _contains(f"{item.name} {item.label}", ("revenue", "sales", "income"))
    )
    workflows = (
        WorkflowEligibility(
            "metric_change_investigation",
            bool(metric_names and time_dimensions),
            tuple(
                reason
                for condition, reason in (
                    (not metric_names, "Define at least one metric."),
                    (not time_dimensions, "Define a date/datetime dimension with month granularity."),
                )
                if condition
            ),
            metric_names,
            time_dimensions,
        ),
        WorkflowEligibility(
            "revenue_investigation",
            bool(revenue_metrics and time_dimensions),
            tuple(
                reason
                for condition, reason in (
                    (not revenue_metrics, "Define a revenue-like metric."),
                    (not time_dimensions, "Define a date/datetime dimension with month granularity."),
                )
                if condition
            ),
            revenue_metrics,
            time_dimensions,
        ),
    )
    queries = _validation_queries(model, freshness_days)
    ready = not any(item.status == "failed" for item in checks) and any(item.eligible for item in workflows)
    return SemanticReadiness(ready, tuple(checks), workflows, queries)


def _validation_queries(model: SemanticModel, freshness_days: int) -> tuple[ValidationQuerySpec, ...]:
    entities = model.entities
    metrics = model.metrics
    dimensions = model.dimensions
    relationships = model.relationships
    by_entity = {item.name: item for item in entities}
    specs: list[ValidationQuerySpec] = []
    for entity in entities:
        table = _quote(entity.source_table)
        key = _quote(entity.primary_key)
        specs.extend(
            (
                _query(
                    f"pk_null.{entity.name}",
                    "null",
                    f"Null primary keys in {entity.name}",
                    "error",
                    f"select count(*) as invalid_count from {table} where {key} is null",
                    {"operator": "equals", "value": 0, "column": "invalid_count"},
                    {"entity": entity.name, "column": entity.primary_key},
                ),
                _query(
                    f"pk_duplicate.{entity.name}",
                    "duplicate",
                    f"Duplicate primary keys in {entity.name}",
                    "error",
                    f"select count(*) as invalid_count from (select {key} from {table} "
                    f"where {key} is not null group by {key} having count(*) > 1) as duplicate_keys",
                    {"operator": "equals", "value": 0, "column": "invalid_count"},
                    {"entity": entity.name, "column": entity.primary_key},
                ),
            )
        )
    for metric in metrics:
        entity = by_entity[metric.entity]
        specs.append(
            _query(
                f"metric_null.{metric.name}",
                "null",
                f"Null values for {metric.label}",
                "warning",
                f"select count(*) as invalid_count from {_quote(entity.source_table)} "
                f"where {_quote(metric.expression)} is null",
                {"operator": "observe", "column": "invalid_count"},
                {"metric": metric.name, "entity": entity.name, "column": metric.expression},
            )
        )
    for dimension in dimensions:
        if dimension.time_granularities:
            entity = by_entity[dimension.entity]
            specs.append(
                _query(
                    f"freshness.{dimension.name}",
                    "freshness",
                    f"Freshness of {dimension.label}",
                    "warning",
                    f"select max({_quote(dimension.expression)}) as latest_value from {_quote(entity.source_table)}",
                    {
                        "operator": "fresh_within_days",
                        "days": freshness_days,
                        "column": "latest_value",
                    },
                    {"dimension": dimension.name, "entity": entity.name, "column": dimension.expression},
                )
            )
    for relationship in relationships:
        child = by_entity[relationship.from_entity]
        parent = by_entity[relationship.to_entity]
        child_table = _quote(child.source_table)
        parent_table = _quote(parent.source_table)
        child_key = _quote(relationship.from_column)
        parent_key = _quote(relationship.to_column)
        specs.append(
            _query(
                f"orphan_fk.{relationship.name}",
                "cardinality",
                f"Orphan keys for {relationship.name}",
                "error",
                f"select count(*) as invalid_count from {child_table} as child "
                f"left join {parent_table} as parent on child.{child_key} = parent.{parent_key} "
                f"where child.{child_key} is not null and parent.{parent_key} is null",
                {"operator": "equals", "value": 0, "column": "invalid_count"},
                {"relationship": relationship.name},
            )
        )
        if relationship.cardinality in {"many_to_one", "one_to_one"}:
            specs.append(
                _query(
                    f"relationship_unique.{relationship.name}",
                    "cardinality",
                    f"Target uniqueness for {relationship.name}",
                    "error",
                    f"select count(*) as invalid_count from (select {parent_key} from {parent_table} "
                    f"where {parent_key} is not null group by {parent_key} having count(*) > 1) "
                    "as duplicate_relationship_keys",
                    {"operator": "equals", "value": 0, "column": "invalid_count"},
                    {"relationship": relationship.name, "column": relationship.to_column},
                )
            )
        if relationship.cardinality in {"one_to_many", "one_to_one"}:
            specs.append(
                _query(
                    f"relationship_source_unique.{relationship.name}",
                    "cardinality",
                    f"Source uniqueness for {relationship.name}",
                    "error",
                    f"select count(*) as invalid_count from (select {child_key} from {child_table} "
                    f"where {child_key} is not null group by {child_key} having count(*) > 1) "
                    "as duplicate_relationship_sources",
                    {"operator": "equals", "value": 0, "column": "invalid_count"},
                    {"relationship": relationship.name, "column": relationship.from_column},
                )
            )
    return tuple(specs)


def _query(
    identifier: str,
    kind: str,
    title: str,
    severity: str,
    sql: str,
    expectation: dict[str, object],
    subject: dict[str, str],
) -> ValidationQuerySpec:
    return ValidationQuerySpec(identifier, kind, title, severity, sql, expectation, subject)


def _ineligible_workflows() -> tuple[WorkflowEligibility, ...]:
    return (
        WorkflowEligibility("metric_change_investigation", False, ("Fix semantic model errors first.",)),
        WorkflowEligibility("revenue_investigation", False, ("Fix semantic model errors first.",)),
    )


def _connected_entities(
    entities: Iterable[SemanticEntity],
    relationships: Iterable[SemanticRelationship],
    preferred_roots: Iterable[str],
) -> set[str]:
    names = [item.name for item in entities]
    if not names:
        return set()
    adjacency: dict[str, set[str]] = {name: set() for name in names}
    for relationship in relationships:
        left = relationship.from_entity
        right = relationship.to_entity
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited: set[str] = set()
    root = next((name for name in preferred_roots if name in adjacency), names[0])
    pending = [root]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current] - visited)
    return visited


def _tables(tables: Sequence[TableSchema] | Mapping[str, TableSchema]) -> list[TableSchema]:
    values = tables.values() if isinstance(tables, Mapping) else tables
    return sorted(values, key=lambda item: item.name.casefold())


def _primary_key(table: TableSchema) -> tuple[str | None, Confidence, str]:
    declared = [column.name for column in table.columns if column.primary_key]
    if declared:
        reason = f"Declared primary key on {table.name}.{declared[0]}."
        if len(declared) > 1:
            reason += " The current semantic contract supports one key; review this composite key."
        return declared[0], "high" if len(declared) == 1 else "medium", reason
    unique = next((index.columns[0] for index in table.indexes if index.unique and len(index.columns) == 1), None)
    if unique:
        return unique, "medium", f"Unique index on {table.name}.{unique} used as a proposed key."
    conventional_names = {"id", f"{table.name}_id"}
    conventional = next((column.name for column in table.columns if column.name.casefold() in conventional_names), None)
    if conventional:
        return conventional, "low", f"Conventional identifier name {table.name}.{conventional}; no key is declared."
    if table.columns:
        return table.columns[0].name, "low", f"First column selected because {table.name} has no declared key."
    return None, "low", f"Table {table.name} has no columns."


def _metric(name: str, label: str, entity: str, aggregation: str, expression: str) -> dict[str, object]:
    return {
        "name": name,
        "label": label,
        "description": "Draft metric inferred from schema metadata",
        "entity": entity,
        "aggregation": aggregation,
        "expression": expression,
        "filters": [],
        "format": "number",
    }


def _dimension(
    name: str,
    label: str,
    entity: str,
    expression: str,
    data_type: str,
    grains: list[str],
) -> dict[str, object]:
    return {
        "name": name,
        "label": label,
        "description": "Draft dimension inferred from schema metadata",
        "entity": entity,
        "expression": expression,
        "data_type": data_type,
        "time_granularities": grains,
    }


def _is_numeric(column: Column) -> bool:
    value = _normal_type(column.type)
    return any(token in value for token in _NUMERIC_TYPES) and "bool" not in value


def _is_temporal(column: Column) -> bool:
    value = _normal_type(column.type)
    return any(token in value for token in _DATE_TYPES) or _contains(
        column.name, ("date", "time", "created_at", "updated_at", "occurred_at")
    )


def _is_categorical(column: Column) -> bool:
    if _contains(column.name, _UNSUITABLE_DIMENSION_NAMES):
        return False
    return any(token in _normal_type(column.type) for token in _TEXT_TYPES) and _contains(
        column.name, _CATEGORICAL_NAMES
    )


def _data_type(column: Column) -> str:
    return "boolean" if "bool" in _normal_type(column.type) else "text"


def _normal_type(value: str) -> str:
    return value.strip().casefold()


def _contains(value: str, candidates: Iterable[str]) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", value.casefold()))
    return any(set(re.findall(r"[a-z0-9]+", candidate.casefold())).issubset(tokens) for candidate in candidates)


def _identifier(value: str) -> str:
    result = re.sub(r"[^a-z0-9_]+", "_", value.casefold()).strip("_") or "item"
    if result[0].isdigit():
        result = f"item_{result}"
    return result


def _unique_name(candidate: str, used: set[str]) -> str:
    value = candidate
    suffix = 2
    while value in used:
        value = f"{candidate}_{suffix}"
        suffix += 1
    used.add(value)
    return value


def _label(value: str) -> str:
    return re.sub(r"[_\-]+", " ", value).strip().title()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = [
    "ReadinessCheck",
    "SemanticDraft",
    "SemanticReadiness",
    "SemanticSuggestion",
    "ValidationQuerySpec",
    "WorkflowEligibility",
    "infer_semantic_draft",
    "semantic_readiness",
]
