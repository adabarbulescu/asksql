from __future__ import annotations

import csv
import json
from io import StringIO

from asksql.models import QueryResult


ExportFormat = str


def format_result(result: QueryResult, output_format: ExportFormat) -> str:
    if output_format == "csv":
        return _csv(result)
    if output_format == "json":
        return json.dumps([dict(zip(result.columns, row)) for row in result.rows], indent=2, default=str) + "\n"
    if output_format == "markdown":
        return _markdown(result)
    raise ValueError(f"unsupported format: {output_format}")


def _csv(result: QueryResult) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(result.columns)
    writer.writerows(result.rows)
    return output.getvalue()


def _markdown(result: QueryResult) -> str:
    if not result.columns:
        return "(no columns)\n"
    lines = [
        "| " + " | ".join(result.columns) + " |",
        "| " + " | ".join("---" for _ in result.columns) + " |",
    ]
    lines.extend("| " + " | ".join(_markdown_cell(value) for value in row) + " |" for row in result.rows)
    return "\n".join(lines) + "\n"


def _markdown_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")
