from __future__ import annotations

import argparse
import sys

from asksql.demo import create_demo_db
from asksql.llm import generate_sql
from asksql.safety import is_read_only
from asksql.sqlite import query, schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask your database questions from the terminal.")
    parser.add_argument("--model", default="ollama:qwen2.5-coder", help="ollama:name or openai:name")
    parser.add_argument("--dry-run", action="store_true", help="show SQL without running it")
    parser.add_argument("db_url", nargs="?", help="database URL, starting with sqlite://..., or demo")
    parser.add_argument("question", nargs="?", help="natural-language question")
    args = parser.parse_args(argv)

    if not args.db_url or not args.question:
        parser.print_help()
        return 0

    db_url = create_demo_db() if args.db_url == "demo" else args.db_url
    sql = generate_sql(args.model, schema(db_url), args.question)
    print("Generated SQL:\n")
    print(sql)

    if args.dry_run:
        return 0
    if not is_read_only(sql):
        print("\nRefusing to run non-read-only SQL.", file=sys.stderr)
        return 2

    columns, rows = query(db_url, sql)
    print()
    print_table(columns, rows)
    return 0


def print_table(columns: list[str], rows: list[tuple[object, ...]]) -> None:
    if not columns:
        print("(no columns)")
        return
    values = [[str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in values:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    print(" | ".join(value.ljust(width) for value, width in zip(columns, widths)))
    print("-+-".join("-" * width for width in widths))
    for row in values:
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))


if __name__ == "__main__":
    raise SystemExit(main())
