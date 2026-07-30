from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from asksql.safety import is_read_only


def evaluate_sql(
    sql: str,
    *,
    dialect: str,
    required_tables: set[str] | None = None,
    forbidden_tables: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not is_read_only(sql, dialect):
        errors.append("SQL must be one read-only statement")
    try:
        statements = [statement for statement in sqlglot.parse(sql, read=dialect) if statement is not None]
    except ParseError as exc:
        return [*errors, f"SQL must parse as {dialect}: {exc}"]
    if len(statements) != 1:
        return [*errors, "SQL must contain exactly one statement"]

    tables = {table.name for table in statements[0].find_all(exp.Table)}
    for table in sorted(required_tables or set()):
        if table not in tables:
            errors.append(f"SQL must use table: {table}")
    for table in sorted(forbidden_tables or set()):
        if table in tables:
            errors.append(f"SQL must not use table: {table}")
    return errors
