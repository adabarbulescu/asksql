from __future__ import annotations

from typing import Protocol

from asksql.models import CancellationToken, MutationResult, QueryResult, SchemaDetails


class DatabaseAdapter(Protocol):
    dialect: str

    def validate(self) -> int: ...

    def schema(self, table_names: list[str] | None = None) -> str: ...

    def inspect_details(self) -> SchemaDetails: ...

    def query(
        self, sql: str, limit: int, timeout: float | None, cancellation: CancellationToken | None
    ) -> QueryResult: ...

    def execute_write(
        self, sql: str, timeout: float | None, cancellation: CancellationToken | None
    ) -> MutationResult: ...

    def explain(self, sql: str) -> QueryResult: ...


def format_schema(details: SchemaDetails, table_names: list[str] | None = None) -> str:
    lines: list[str] = []
    for table in details.tables.values():
        if table_names is not None and table.name not in table_names:
            continue
        lines.append(f"{table.name}(")
        for column in table.columns:
            parts = [f"  {column.name} {column.type}".rstrip()]
            if column.primary_key:
                parts.append("PRIMARY KEY")
            foreign_key = next((key for key in table.foreign_keys if key.column == column.name), None)
            if foreign_key:
                parts.append(f"REFERENCES {foreign_key.referenced_table}({foreign_key.referenced_column})")
            lines.append(" ".join(parts) + ",")
        lines[-1] = lines[-1].rstrip(",")
        lines.extend((")", ""))
    return "\n".join(lines) or "(empty schema)"
