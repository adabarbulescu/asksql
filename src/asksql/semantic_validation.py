from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from asksql.models import CancellationToken, QueryResult
from asksql.semantic_bootstrap import SemanticReadiness, ValidationQuerySpec
from asksql.sqlite import DEFAULT_TIMEOUT


class ValidationAdapter(Protocol):
    def query(
        self,
        sql: str,
        limit: int,
        timeout: float | None,
        cancellation: CancellationToken | None,
        parameters: dict[str, object] | None = None,
    ) -> QueryResult: ...


@dataclass(frozen=True)
class ValidationResult:
    id: str
    title: str
    status: str
    severity: str
    observed: object | None
    message: str
    sql: str
    subject: dict[str, str]

    def payload(self) -> dict[str, object]:
        return asdict(self)


def evaluate_validation_queries(
    adapter: ValidationAdapter,
    readiness: SemanticReadiness,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Execute bounded, read-only trust checks and merge them into readiness."""

    instant = now or datetime.now(UTC)
    results = tuple(_evaluate(adapter, spec, instant) for spec in readiness.validation_queries)
    payload = readiness.payload()
    payload["validation_results"] = [item.payload() for item in results]
    payload["ready"] = bool(payload["ready"]) and not any(
        item.status in {"failed", "error"} and item.severity == "error" for item in results
    )
    return payload


def _evaluate(adapter: ValidationAdapter, spec: ValidationQuerySpec, now: datetime) -> ValidationResult:
    try:
        result = adapter.query(spec.sql, limit=1, timeout=DEFAULT_TIMEOUT, cancellation=None)
        observed = _value(result, str(spec.expectation["column"]))
        passed, message = _matches(spec, observed, now)
        status = "passed" if passed else ("failed" if spec.severity == "error" else "warning")
        return ValidationResult(spec.id, spec.title, status, spec.severity, observed, message, spec.sql, spec.subject)
    except Exception as exc:
        return ValidationResult(
            spec.id,
            spec.title,
            "error",
            spec.severity,
            None,
            f"Validation query could not run: {exc}",
            spec.sql,
            spec.subject,
        )


def _value(result: QueryResult, column: str) -> object | None:
    if column not in result.columns or not result.rows:
        return None
    return result.rows[0][result.columns.index(column)]


def _matches(spec: ValidationQuerySpec, observed: object | None, now: datetime) -> tuple[bool, str]:
    operator = spec.expectation.get("operator")
    if operator == "equals":
        expected = spec.expectation.get("value")
        passed = observed == expected
        return passed, f"Observed {observed!r}; expected {expected!r}."
    if operator == "observe":
        count = _integer(observed, 0)
        return count == 0, f"Observed {count} row(s)."
    if operator == "fresh_within_days":
        days = _integer(spec.expectation.get("days"), 0)
        latest = _as_datetime(observed)
        if latest is None:
            return False, "No latest timestamp was observed."
        age = (now.date() - latest.date()).days
        return age <= days, f"Latest value is {age} day(s) old; threshold is {days}."
    return False, f"Unsupported validation operator: {operator!r}."


def _as_datetime(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                return None
            return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _integer(value: object | None, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except ValueError:
            return default
    return default
