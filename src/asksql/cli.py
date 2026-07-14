from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from asksql.demo import create_demo_db
from asksql.llm import generate_sql, ollama_models
from asksql.safety import is_read_only
from asksql.sqlite import query, schema

console = Console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask your database questions from the terminal.")
    parser.add_argument("--model", default="ollama:qwen2.5-coder:7b", help="ollama:name or openai:name")
    parser.add_argument("--dry-run", action="store_true", help="show SQL without running it")
    parser.add_argument("-y", "--yes", action="store_true", help="run read-only SQL without prompting")
    parser.add_argument("--show-schema", action="store_true", help="print the schema sent to the model")
    parser.add_argument("db_url", nargs="?", help="database URL, demo, or models")
    parser.add_argument("question", nargs="?", help="natural-language question")
    args = parser.parse_args(argv)

    if args.db_url == "models":
        return show_models()

    if not args.db_url or not args.question:
        parser.print_help()
        return 0

    db_url = create_demo_db() if args.db_url == "demo" else args.db_url
    try:
        db_schema = schema(db_url)
        if args.show_schema:
            console.print(Panel(db_schema, title="Schema", border_style="blue"))
        with console.status(f"Asking {args.model}...", spinner="dots"):
            sql = generate_sql(args.model, db_schema, args.question)
    except Exception as exc:
        console.print(f"[red]Error:[/] {exc}", file=sys.stderr)
        return 1

    console.print(Panel(Syntax(sql, "sql", theme="ansi_dark"), title="Generated SQL", border_style="green"))

    if args.dry_run:
        return 0
    if not is_read_only(sql):
        console.print("[red]Refusing to run non-read-only SQL.[/]", file=sys.stderr)
        return 2
    if not args.yes and not confirm_run():
        return 1

    try:
        columns, rows = query(db_url, sql)
    except Exception as exc:
        console.print(f"[red]Query failed:[/] {exc}", file=sys.stderr)
        return 1
    print_table(columns, rows)
    return 0


def print_table(columns: list[str], rows: list[tuple[object, ...]]) -> None:
    if not columns:
        console.print("[dim](no columns)[/]")
        return
    table = Table(title=f"{len(rows)} rows", show_lines=False)
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


def confirm_run() -> bool:
    return bool(sys.stdin.isatty() and Confirm.ask("Run this read-only query?", default=False))


def show_models() -> int:
    try:
        models = ollama_models()
    except Exception as exc:
        console.print(f"[red]Could not reach Ollama:[/] {exc}", file=sys.stderr)
        return 1
    table = Table(title="Ollama models")
    table.add_column("name")
    table.add_column("size", justify="right")
    for model in models:
        table.add_row(str(model.get("name", "")), format_size(int(model.get("size", 0))))
    console.print(table)
    return 0


def format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} GB"


if __name__ == "__main__":
    raise SystemExit(main())
