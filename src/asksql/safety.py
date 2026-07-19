from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

READ_ONLY_PRAGMAS = {
    "database_list",
    "foreign_key_list",
    "index_info",
    "index_list",
    "index_xinfo",
    "table_info",
    "table_list",
    "table_xinfo",
}
WRITE_NODES = (
    exp.Alter,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Update,
)
DANGEROUS_NODES = (
    exp.Alter,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.TruncateTable,
    exp.Update,
)


def is_read_only(sql: str, dialect: str = "sqlite") -> bool:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return False
    lowered = sql.lower()
    if lowered.startswith("explain query plan "):
        return is_read_only(sql[19:], dialect)
    if lowered.startswith("explain "):
        return is_read_only(sql[8:], dialect)
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except ParseError:
        return False
    if len(statements) != 1:
        return False
    statement = statements[0]
    return bool(statement and _is_read_only_expression(cast(exp.Expression, statement)))


def is_write(sql: str, dialect: str = "sqlite") -> bool:
    """Return whether SQL is one supported, explicitly mutating SQLite statement."""
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return False
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except ParseError:
        return False
    if len(statements) != 1 or statements[0] is None:
        return False
    return isinstance(cast(exp.Expression, statements[0]), WRITE_NODES)


def _is_read_only_expression(statement: exp.Expression) -> bool:
    if any(isinstance(node, DANGEROUS_NODES) for node in statement.walk()):
        return False
    if isinstance(statement, exp.Query):
        return True
    if isinstance(statement, exp.Pragma):
        return _pragma_name(statement) in READ_ONLY_PRAGMAS
    return False


def _pragma_name(statement: exp.Pragma) -> str:
    node = statement.this
    if isinstance(node, exp.EQ):
        node = node.this
    return str(node.this if isinstance(node, exp.Var) else node).lower()
