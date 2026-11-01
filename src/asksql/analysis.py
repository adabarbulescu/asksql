from __future__ import annotations

import textwrap
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence

from asksql.models import CancellationToken, ExecutionStatus, QueryResult
from asksql.semantic import SemanticModel, SemanticQueryPlan, compile_query
from asksql.service import QueryService

ANALYSIS_STATES = {"draft", "planning", "running", "completed", "partially_completed", "failed", "cancelled"}


class AnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisDefinition:
    id: str
    name: str
    description: str
    template: str
    goal: str
    semantic_model_id: str
    inputs: tuple[dict[str, object], ...]
    steps: tuple[dict[str, object], ...]
    outputs: tuple[str, ...]
    created_at: str = ""
    updated_at: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "goal": self.goal,
            "semantic_model_id": self.semantic_model_id,
            "inputs": [dict(item) for item in self.inputs],
            "steps": [dict(item) for item in self.steps],
            "outputs": list(self.outputs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PlannedStep:
    id: str
    title: str
    kind: str
    plan: SemanticQueryPlan
    depends_on: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
            "plan": self.plan.payload(),
        }


def definition_from_payload(
    payload: Mapping[str, Any], *, identifier: str = "", created_at: str = "", updated_at: str = ""
) -> AnalysisDefinition:
    steps = _object_tuple(payload.get("steps"), "steps")
    inputs = _object_tuple(payload.get("inputs", []), "inputs")
    outputs_raw = payload.get("outputs", [])
    if not isinstance(outputs_raw, list) or not all(isinstance(item, str) for item in outputs_raw):
        raise AnalysisError("outputs must be a list of names")
    definition = AnalysisDefinition(
        id=identifier,
        name=_text(payload, "name", 200),
        description=str(payload.get("description", "")).strip()[:2_000],
        template=_text(payload, "template", 100),
        goal=_text(payload, "goal", 2_000),
        semantic_model_id=_text(payload, "semantic_model_id", 64),
        inputs=inputs,
        steps=steps,
        outputs=tuple(outputs_raw),
        created_at=created_at,
        updated_at=updated_at,
    )
    _validate_definition(definition)
    return definition


def revenue_investigation_definition(model: SemanticModel, *, identifier: str = "") -> AnalysisDefinition:
    revenue = _find_metric(model, ("revenue", "sales", "income"))
    time_dimension = next((item for item in model.dimensions if "month" in item.time_granularities), None)
    if revenue is None or time_dimension is None:
        raise AnalysisError("Revenue Investigation requires a revenue-like metric and a monthly time dimension")
    orders = _find_metric(model, ("orders", "order_count", "completed_orders"))
    slices = [item for item in model.dimensions if item.name != time_dimension.name and not item.time_granularities][:3]
    steps: list[dict[str, object]] = [
        {"id": "revenue_change", "type": "period_comparison", "metric": revenue.name, "depends_on": []},
        {
            "id": "revenue_trend",
            "type": "trend",
            "metric": revenue.name,
            "dimension": time_dimension.name,
            "grain": "month",
            "depends_on": ["revenue_change"],
        },
    ]
    if orders:
        steps.append(
            {
                "id": "metric_decomposition",
                "type": "metric_decomposition",
                "metric": revenue.name,
                "components": [orders.name],
                "depends_on": ["revenue_change"],
            }
        )
    for dimension in slices:
        steps.append(
            {
                "id": f"{dimension.name}_contribution",
                "type": "dimensional_contribution",
                "metric": revenue.name,
                "dimension": dimension.name,
                "top_n": 10,
                "depends_on": ["revenue_change"],
            }
        )
    payload: dict[str, object] = {
        "name": "Revenue Investigation",
        "description": "Explain revenue change through metric decomposition and dimensional contributions.",
        "template": "revenue_investigation",
        "goal": "Explain why revenue changed between two comparable periods.",
        "semantic_model_id": model.id,
        "inputs": [
            {"name": "current_start", "type": "date", "required": True},
            {"name": "current_end", "type": "date", "required": True},
            {"name": "previous_start", "type": "date", "required": True},
            {"name": "previous_end", "type": "date", "required": True},
        ],
        "steps": steps,
        "outputs": ["executive_summary", "findings", "charts", "evidence", "follow_up_actions"],
    }
    return definition_from_payload(payload, identifier=identifier)


def plan_analysis(
    definition: AnalysisDefinition, model: SemanticModel, inputs: Mapping[str, object]
) -> list[PlannedStep]:
    if definition.semantic_model_id != model.id:
        raise AnalysisError("analysis definition references a different semantic model")
    _validate_inputs(definition, inputs)
    ordered = _topological_steps(definition.steps)
    time_dimension = _analysis_time_dimension(model, ordered)
    scope_filters = _scope_filters(inputs)
    current_filters = _period_filters(time_dimension, inputs, "current", scope_filters)
    previous_filters = _period_filters(time_dimension, inputs, "previous", scope_filters)
    all_filters = _period_filters(time_dimension, inputs, "all", scope_filters)
    planned: list[PlannedStep] = []
    for step in ordered:
        identifier = str(step["id"])
        kind = str(step["type"])
        metric = str(step.get("metric", ""))
        dependencies_raw = step.get("depends_on", [])
        if not isinstance(dependencies_raw, list):
            raise AnalysisError(f"invalid dependencies for step {identifier}")
        dependencies = tuple(str(item) for item in dependencies_raw)
        if kind == "period_comparison":
            planned.extend(
                [
                    _planned(
                        f"{identifier}.current",
                        "Current period",
                        kind,
                        model,
                        [metric],
                        [],
                        current_filters,
                        dependencies,
                    ),
                    _planned(
                        f"{identifier}.previous",
                        "Previous period",
                        kind,
                        model,
                        [metric],
                        [],
                        previous_filters,
                        dependencies,
                    ),
                ]
            )
        elif kind == "trend":
            dimension = str(step.get("dimension", ""))
            grain = str(step.get("grain", "month"))
            planned.append(
                _planned(
                    identifier,
                    "Revenue trend",
                    kind,
                    model,
                    [metric],
                    [{"name": dimension, "granularity": grain}],
                    all_filters,
                    dependencies,
                )
            )
        elif kind == "metric_decomposition":
            components = step.get("components", [])
            if not isinstance(components, list):
                raise AnalysisError(f"invalid components for step {identifier}")
            for component in components:
                name = str(component)
                planned.extend(
                    [
                        _planned(
                            f"{identifier}.{name}.current",
                            f"Current {name}",
                            kind,
                            model,
                            [name],
                            [],
                            current_filters,
                            dependencies,
                        ),
                        _planned(
                            f"{identifier}.{name}.previous",
                            f"Previous {name}",
                            kind,
                            model,
                            [name],
                            [],
                            previous_filters,
                            dependencies,
                        ),
                    ]
                )
        elif kind == "dimensional_contribution":
            dimension = str(step.get("dimension", ""))
            planned.extend(
                [
                    _planned(
                        f"{identifier}.current",
                        f"Current by {dimension}",
                        kind,
                        model,
                        [metric],
                        [{"name": dimension, "granularity": None}],
                        current_filters,
                        dependencies,
                    ),
                    _planned(
                        f"{identifier}.previous",
                        f"Previous by {dimension}",
                        kind,
                        model,
                        [metric],
                        [{"name": dimension, "granularity": None}],
                        previous_filters,
                        dependencies,
                    ),
                ]
            )
        else:
            raise AnalysisError(f"unsupported analysis step type: {kind}")
    if len(planned) > 30:
        raise AnalysisError("analysis exceeds the 30-query execution budget")
    return planned


class AnalysisEngine:
    def __init__(self, service: QueryService, *, query_limit: int = 2_000, query_timeout: float = 30) -> None:
        self.service = service
        self.query_limit = query_limit
        self.query_timeout = query_timeout

    def execute(
        self,
        definition: AnalysisDefinition,
        model: SemanticModel,
        inputs: Mapping[str, object],
        *,
        cancellation: CancellationToken | None = None,
        progress: Callable[[list[dict[str, object]], list[dict[str, object]]], None] | None = None,
    ) -> dict[str, object]:
        token = cancellation or CancellationToken()
        planned = plan_analysis(definition, model, inputs)
        steps = [{**item.payload(), "state": "queued", "error": None} for item in planned]
        evidence: list[dict[str, object]] = []
        for index, planned_step in enumerate(planned):
            if token.cancelled:
                for pending in steps[index:]:
                    pending["state"] = "cancelled"
                return _analysis_result("cancelled", steps, evidence, definition, model, inputs)
            steps[index]["state"] = "running"
            if progress:
                progress(steps, evidence)
            compiled = compile_query(model, planned_step.plan, self.service.adapter.dialect)
            execution = self.service.execute(
                compiled.sql,
                limit=self.query_limit,
                timeout=self.query_timeout,
                cancellation=token,
                parameters=compiled.parameters,
            )
            steps[index]["state"] = "completed" if execution.status == ExecutionStatus.SUCCEEDED else "failed"
            steps[index]["error"] = execution.error
            evidence.append(_evidence(planned_step, compiled.payload(), execution))
            if progress:
                progress(steps, evidence)
        succeeded = sum(item["state"] == "completed" for item in steps)
        state = "completed" if succeeded == len(steps) else "partially_completed" if succeeded else "failed"
        return _analysis_result(state, steps, evidence, definition, model, inputs)


def report_as_html(run: Mapping[str, Any]) -> str:
    report_raw = run.get("report")
    findings_raw = run.get("findings")
    evidence_raw = run.get("evidence")
    report: Mapping[str, Any] = report_raw if isinstance(report_raw, Mapping) else {}
    findings: list[Any] = findings_raw if isinstance(findings_raw, list) else []
    evidence: list[Any] = evidence_raw if isinstance(evidence_raw, list) else []
    title = _escape(str(run.get("definition_name", "AskSQL Analysis")))
    finding_html = "".join(
        f"<article><h3>{_escape(str(item.get('title', 'Finding')))}</h3>"
        f"<p>{_escape(str(item.get('claim', '')))}</p></article>"
        for item in findings
        if isinstance(item, Mapping)
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + title
        + "</title><style>body{font:15px system-ui;max-width:900px;margin:40px auto;color:#20242c}"
        "h1{font-size:30px}h2{margin-top:35px}article{border-left:3px solid #7565d8;padding:2px 16px;margin:18px 0}"
        ".meta{color:#667085}code{font-size:12px}</style></head><body>"
        f"<h1>{title}</h1><p class='meta'>Generated by AskSQL · {run.get('state', '')}</p>"
        f"<h2>{_escape(str(report.get('headline', 'Analysis report')))}</h2>"
        f"<p>{_escape(str(report.get('summary', '')))}</p><h2>Findings</h2>{finding_html}"
        f"<h2>Evidence</h2><p>{len(evidence)} semantic queries retained with lineage.</p>"
        "</body></html>"
    )


def report_as_pdf(run: Mapping[str, Any]) -> bytes:
    report_raw = run.get("report")
    findings_raw = run.get("findings")
    evidence_raw = run.get("evidence")
    report: Mapping[str, Any] = report_raw if isinstance(report_raw, Mapping) else {}
    findings: list[Any] = findings_raw if isinstance(findings_raw, list) else []
    evidence: list[Any] = evidence_raw if isinstance(evidence_raw, list) else []
    lines = [
        str(run.get("definition_name", "AskSQL Analysis")),
        str(report.get("headline", "Analysis report")),
        "",
        str(report.get("summary", "")),
        "",
        "Findings",
    ]
    for item in findings:
        if isinstance(item, Mapping):
            lines.extend([f"- {item.get('title', 'Finding')}: {item.get('claim', '')}"])
    lines.extend(["", f"Evidence: {len(evidence)} semantic queries"])
    wrapped = [part for line in lines for part in (textwrap.wrap(line, 90) or [""])]
    return _simple_pdf(wrapped[:55])


def _analysis_result(
    state: str,
    steps: list[dict[str, object]],
    evidence: list[dict[str, object]],
    definition: AnalysisDefinition,
    model: SemanticModel,
    inputs: Mapping[str, object],
) -> dict[str, object]:
    findings, charts, report = _diagnose(definition, model, inputs, evidence)
    return {
        "state": state,
        "steps": steps,
        "evidence": evidence,
        "findings": findings,
        "charts": charts,
        "report": report,
    }


def _diagnose(
    definition: AnalysisDefinition,
    model: SemanticModel,
    inputs: Mapping[str, object],
    evidence: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    del model
    successful = [item for item in evidence if item.get("status") == "succeeded"]
    by_step = {str(item["step_id"]): item for item in successful}
    findings: list[dict[str, object]] = []
    charts: list[dict[str, object]] = []
    current = _single_metric(by_step.get("revenue_change.current"))
    previous = _single_metric(by_step.get("revenue_change.previous"))
    if current is not None and previous is not None:
        delta = current - previous
        percent = delta / abs(previous) * 100 if previous else None
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "was unchanged"
        claim = (
            f"Revenue {direction} by {_format_percent(abs(percent))}."
            if percent is not None
            else f"Revenue {direction}."
        )
        findings.append(
            _finding(
                "revenue_change",
                "Revenue change",
                claim,
                delta,
                direction,
                [by_step["revenue_change.current"]["id"], by_step["revenue_change.previous"]["id"]],
            )
        )
    trend = by_step.get("revenue_trend")
    if trend:
        chart = _chart_from_evidence(trend, "line", "Revenue trend")
        if chart:
            charts.append(chart)
    for step_id in sorted(
        {key.rsplit(".", 1)[0] for key in by_step if key.endswith(".current") and "contribution" in key}
    ):
        current_item, previous_item = by_step.get(f"{step_id}.current"), by_step.get(f"{step_id}.previous")
        if not current_item or not previous_item:
            continue
        contributions = _contributions(current_item, previous_item)
        if not contributions:
            continue
        dimension = step_id.removesuffix("_contribution")
        chart = {
            "id": uuid.uuid4().hex,
            "type": "bar",
            "title": f"Revenue contribution by {dimension}",
            "labels": [str(item[0]) for item in contributions[:10]],
            "series": [{"name": "Contribution", "values": [item[1] for item in contributions[:10]]}],
            "evidence_ids": [current_item["id"], previous_item["id"]],
        }
        charts.append(chart)
        driver, contribution = min(contributions, key=lambda item: item[1])
        if contribution < 0:
            findings.append(
                _finding(
                    f"{step_id}.driver",
                    f"{dimension.title()} driver",
                    f"{driver} contributed {_format_number(contribution)} to the revenue decline.",
                    contribution,
                    "decreased",
                    [current_item["id"], previous_item["id"]],
                    {"definition_id": definition.id, "scope_filters": [{"dimension": dimension, "value": driver}]},
                )
            )
    orders_current = next(
        (
            _single_metric(item)
            for key, item in by_step.items()
            if key.startswith("metric_decomposition.") and key.endswith(".current")
        ),
        None,
    )
    orders_previous = next(
        (
            _single_metric(item)
            for key, item in by_step.items()
            if key.startswith("metric_decomposition.") and key.endswith(".previous")
        ),
        None,
    )
    if None not in (current, previous, orders_current, orders_previous) and orders_current and orders_previous:
        aov_current = current / orders_current  # type: ignore[operator]
        aov_previous = previous / orders_previous  # type: ignore[operator]
        order_change = (orders_current - orders_previous) / abs(orders_previous) * 100
        aov_change = (aov_current - aov_previous) / abs(aov_previous) * 100 if aov_previous else 0
        dominant = "order volume" if abs(order_change) >= abs(aov_change) else "average order value"
        findings.append(
            _finding(
                "metric_decomposition",
                "Metric decomposition",
                f"The larger measurable driver was {dominant}: "
                f"orders changed {_format_signed_percent(order_change)}, "
                f"while AOV changed {_format_signed_percent(aov_change)}.",
                max(abs(order_change), abs(aov_change)),
                "mixed",
                [item["id"] for key, item in by_step.items() if key.startswith("metric_decomposition.")],
            )
        )
    coverage = len(successful) / len(evidence) if evidence else 0
    completeness = sum(not item.get("quality_flags") for item in successful) / len(successful) if successful else 0
    confidence_score = round(100 * (0.65 * coverage + 0.35 * completeness))
    confidence = "high" if confidence_score >= 85 else "medium" if confidence_score >= 60 else "low"
    headline = findings[0]["claim"] if findings else "The analysis did not produce sufficient evidence."
    summary = " ".join(str(item["claim"]) for item in findings[:4])
    report = {
        "headline": headline,
        "summary": summary,
        "confidence": confidence,
        "confidence_score": confidence_score,
        "confidence_basis": {
            "evidence_coverage": round(coverage * 100),
            "data_completeness": round(completeness * 100),
        },
        "current_period": [inputs.get("current_start"), inputs.get("current_end")],
        "comparison_period": [inputs.get("previous_start"), inputs.get("previous_end")],
    }
    return findings, charts, report


def _planned(
    identifier: str,
    title: str,
    kind: str,
    model: SemanticModel,
    metrics: list[str],
    dimensions: list[dict[str, str | None]],
    filters: list[dict[str, object]],
    depends_on: tuple[str, ...],
) -> PlannedStep:
    metric_names = {item.name for item in model.metrics}
    dimension_names = {item.name for item in model.dimensions}
    if not set(metrics) <= metric_names:
        raise AnalysisError(f"unknown metric in analysis step {identifier}")
    if not {str(item["name"]) for item in dimensions} <= dimension_names:
        raise AnalysisError(f"unknown dimension in analysis step {identifier}")
    return PlannedStep(
        identifier,
        title,
        kind,
        SemanticQueryPlan(model.id, tuple(metrics), tuple(dimensions), tuple(filters)),
        depends_on,
    )


def _period_filters(
    dimension: str, inputs: Mapping[str, object], period: str, scope: list[dict[str, object]]
) -> list[dict[str, object]]:
    if period == "all":
        start = min(str(inputs["current_start"]), str(inputs["previous_start"]))
        end = max(str(inputs["current_end"]), str(inputs["previous_end"]))
    else:
        start, end = str(inputs[f"{period}_start"]), str(inputs[f"{period}_end"])
    return [
        {"dimension": dimension, "operator": "gte", "value": start},
        {"dimension": dimension, "operator": "lt", "value": end},
        *scope,
    ]


def _scope_filters(inputs: Mapping[str, object]) -> list[dict[str, object]]:
    raw = inputs.get("scope_filters", [])
    if not isinstance(raw, list):
        raise AnalysisError("scope_filters must be a list")
    filters: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("dimension"), str):
            raise AnalysisError("invalid scope filter")
        filters.append({"dimension": item["dimension"], "operator": "eq", "value": item.get("value")})
    return filters


def _analysis_time_dimension(model: SemanticModel, steps: Sequence[dict[str, object]]) -> str:
    trend = next((step for step in steps if step.get("type") == "trend"), None)
    if trend and isinstance(trend.get("dimension"), str):
        return str(trend["dimension"])
    candidate = next((item for item in model.dimensions if item.time_granularities), None)
    if candidate is None:
        raise AnalysisError("analysis requires a time dimension")
    return candidate.name


def _validate_inputs(definition: AnalysisDefinition, inputs: Mapping[str, object]) -> None:
    for item in definition.inputs:
        name = str(item.get("name", ""))
        if item.get("required") and inputs.get(name) in (None, ""):
            raise AnalysisError(f"analysis input {name} is required")
    for name in ("current_start", "current_end", "previous_start", "previous_end"):
        try:
            date.fromisoformat(str(inputs[name]))
        except (KeyError, ValueError) as exc:
            raise AnalysisError(f"analysis input {name} must be an ISO date") from exc
    if str(inputs["current_start"]) >= str(inputs["current_end"]):
        raise AnalysisError("current period start must precede its end")
    if str(inputs["previous_start"]) >= str(inputs["previous_end"]):
        raise AnalysisError("previous period start must precede its end")


def _validate_definition(definition: AnalysisDefinition) -> None:
    identifiers = [str(item.get("id", "")) for item in definition.steps]
    if any(not identifier for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise AnalysisError("analysis step identifiers must be non-empty and unique")
    _topological_steps(definition.steps)


def _topological_steps(steps: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_id = {str(item.get("id")): item for item in steps}
    pending = set(by_id)
    completed: set[str] = set()
    ordered: list[dict[str, object]] = []
    while pending:
        ready: list[str] = []
        for identifier in sorted(pending):
            raw_dependencies = by_id[identifier].get("depends_on", [])
            if not isinstance(raw_dependencies, list):
                raise AnalysisError(f"invalid dependencies for step {identifier}")
            if set(str(item) for item in raw_dependencies) <= completed:
                ready.append(identifier)
        if not ready:
            raise AnalysisError("analysis steps contain a cycle or an unknown dependency")
        for identifier in ready:
            ordered.append(by_id[identifier])
            completed.add(identifier)
            pending.remove(identifier)
    return ordered


def _evidence(step: PlannedStep, compiled: Mapping[str, object], execution: Any) -> dict[str, object]:
    result = execution.result if isinstance(execution.result, QueryResult) else None
    flags: list[str] = []
    if result and result.truncated:
        flags.append("result_truncated")
    if result and not result.rows:
        flags.append("empty_result")
    parameters = compiled.get("parameters", {})
    redacted = (
        {
            key: "***" if any(word in key.lower() for word in ("secret", "password", "token")) else value
            for key, value in parameters.items()
        }
        if isinstance(parameters, Mapping)
        else {}
    )
    return {
        "id": uuid.uuid4().hex,
        "step_id": step.id,
        "title": step.title,
        "semantic_plan": step.plan.payload(),
        "compiled_sql": compiled["sql"],
        "parameters": redacted,
        "columns": list(result.columns) if result else [],
        "rows": [list(row) for row in result.rows] if result else [],
        "row_count": len(result.rows) if result else 0,
        "duration_ms": round(execution.duration_ms, 3),
        "status": execution.status.value,
        "error": execution.error,
        "quality_flags": flags,
    }


def _single_metric(evidence: Mapping[str, object] | None) -> float | None:
    if not evidence:
        return None
    rows = evidence.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], list) or not rows[0]:
        return None
    try:
        return float(rows[0][-1])
    except (TypeError, ValueError):
        return None


def _contributions(current: Mapping[str, object], previous: Mapping[str, object]) -> list[tuple[object, float]]:
    current_values = _dimension_values(current)
    previous_values = _dimension_values(previous)
    keys = set(current_values) | set(previous_values)
    return sorted(
        ((key, current_values.get(key, 0) - previous_values.get(key, 0)) for key in keys),
        key=lambda item: abs(item[1]),
        reverse=True,
    )


def _dimension_values(evidence: Mapping[str, object]) -> dict[object, float]:
    rows = evidence.get("rows")
    if not isinstance(rows, list):
        return {}
    values: dict[object, float] = {}
    for row in rows:
        if isinstance(row, list) and len(row) >= 2:
            try:
                values[row[0]] = float(row[-1])
            except (TypeError, ValueError):
                continue
    return values


def _chart_from_evidence(evidence: Mapping[str, object], kind: str, title: str) -> dict[str, object] | None:
    values = _dimension_values(evidence)
    if not values:
        return None
    ordered = sorted(values.items(), key=lambda item: str(item[0]))
    return {
        "id": uuid.uuid4().hex,
        "type": kind,
        "title": title,
        "labels": [str(item[0]) for item in ordered],
        "series": [{"name": title, "values": [item[1] for item in ordered]}],
        "evidence_ids": [evidence["id"]],
    }


def _finding(
    identifier: str,
    title: str,
    claim: str,
    magnitude: float,
    direction: str,
    evidence_ids: list[object],
    follow_up: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": identifier,
        "title": title,
        "claim": claim,
        "finding_type": "diagnostic",
        "magnitude": magnitude,
        "direction": direction,
        "evidence_ids": evidence_ids,
        "method": "deterministic_comparison",
        "follow_up_analysis": follow_up,
    }


def _find_metric(model: SemanticModel, candidates: Sequence[str]) -> Any:
    for candidate in candidates:
        found = next(
            (
                item
                for item in model.metrics
                if item.name == candidate or candidate in item.name.lower() or candidate in item.label.lower()
            ),
            None,
        )
        if found:
            return found
    return None


def _object_tuple(value: object, name: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AnalysisError(f"{name} must be a list of objects")
    return tuple(dict(item) for item in value)


def _text(payload: Mapping[str, Any], key: str, limit: int) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise AnalysisError(f"{key} cannot be empty")
    return value[:limit]


def _format_percent(value: float | None) -> str:
    return "an unavailable percentage" if value is None else f"{value:.1f}%"


def _format_signed_percent(value: float) -> str:
    return f"{value:+.1f}%"


def _format_number(value: float) -> str:
    return f"{value:+,.2f}"


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _simple_pdf(lines: Sequence[str]) -> bytes:
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 11 Tf 50 790 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode('latin-1', 'replace'))} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, item in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n{item}\nendobj\n".encode("latin-1", "replace"))
    start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode())
    return bytes(output)
