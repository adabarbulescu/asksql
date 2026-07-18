from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from asksql.demo import create_demo_db
from asksql.export import format_result
from asksql.llm import generate_sql, ollama_models
from asksql.safety import is_read_only
from asksql.sql import pretty_sql
from asksql.sqlite import QueryResult, inspect, query_result, schema
from asksql.tui import run_tui

console = Console()
error_console = Console(stderr=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask your database questions from the terminal.")
    parser.add_argument("--model", default="ollama:qwen2.5-coder:7b", help="ollama:name or openai:name")
    parser.add_argument("--dry-run", action="store_true", help="show SQL without running it")
    parser.add_argument("--format", choices=["table", "csv", "json", "markdown"], default="table", help="result output format")
    parser.add_argument("--output", help="write csv/json/markdown output to a file")
    parser.add_argument("--force", action="store_true", help="overwrite --output if it exists")
    parser.add_argument("-y", "--yes", action="store_true", help="run read-only SQL without prompting")
    parser.add_argument("--show-schema", action="store_true", help="print the schema sent to the model")
    parser.add_argument("db_url", nargs="?", help="database URL, demo, models, schema, run, or tui")
    parser.add_argument("question", nargs=argparse.REMAINDER, help="question, schema DB URL, or SQL")
    args = parser.parse_args(argv)
    text = " ".join(args.question).strip()

    if args.db_url == "models":
        return show_models()
    if args.db_url == "schema":
        return show_schema(text or "demo")
    if args.db_url == "run":
        return run_sql_command(text, args.yes, args.format, args.output, args.force)
    if args.db_url == "tui":
        run_tui(create_demo_db() if not text or text == "demo" else text, args.model)
        return 0

    if not args.db_url or not text:
        parser.print_help()
        return 0

    db_url = create_demo_db() if args.db_url == "demo" else args.db_url
    try:
        db_schema = schema(db_url)
        if args.show_schema:
            console.print(Panel(db_schema, title="Schema", border_style="blue"))
        with console.status(f"Asking {args.model}...", spinner="dots"):
            sql = generate_sql(args.model, db_schema, text)
    except Exception as exc:
        error_console.print(f"[red]Error:[/] {exc}")
        return 1

    console.print(Panel(Syntax(sql, "sql", theme="ansi_dark"), title="Generated SQL", border_style="green"))

    if args.dry_run:
        return 0
    if not is_read_only(sql):
        error_console.print("[red]Refusing to run non-read-only SQL.[/]")
        return 2
    if not args.yes and not confirm_run():
        return 1

    try:
        result = query_result(db_url, sql)
    except Exception as exc:
        error_console.print(f"[red]Query failed:[/] {exc}")
        return 1
    return print_result(result, args.format, args.output, args.force)


def print_result(result: QueryResult, output_format: str, output: str | None = None, force: bool = False) -> int:
    if output_format == "table":
        print_table(result)
        return 0
    text = format_result(result, output_format)
    if output:
        path = Path(output)
        if path.exists() and not force:
            error_console.print(f"[red]Output exists:[/] {path} (use --force to overwrite)")
            return 1
        path.write_text(text)
        console.print(f"Wrote {output_format} to {path}")
    else:
        console.print(text, end="")
    if result.truncated:
        error_console.print(f"[yellow]Results limited to {result.limit} rows.[/]")
    return 0


def print_table(result: QueryResult) -> None:
    columns, rows = result.columns, result.rows
    if not columns:
        console.print("[dim](no columns)[/]")
        return
    title = f"{result.limit}+ rows (limited to {result.limit})" if result.truncated else f"{len(rows)} rows"
    table = Table(title=title, show_lines=False)
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(str(value) for value in row))
    console.print(table)


def run_sql_command(text: str, yes: bool, output_format: str = "table", output: str | None = None, force: bool = False) -> int:
    target, _, sql = text.partition(" ")
    if not target or not sql:
        console.print("[red]Usage:[/] asksql run <db-url|demo> \"select ...\"")
        return 1
    db_url = create_demo_db() if target == "demo" else target
    sql = pretty_sql(sql)
    console.print(Panel(Syntax(sql, "sql", theme="ansi_dark"), title="SQL", border_style="green"))
    if not is_read_only(sql):
        error_console.print("[red]Refusing to run non-read-only SQL.[/]")
        return 2
    if not yes and not confirm_run():
        return 1
    try:
        result = query_result(db_url, sql)
    except Exception as exc:
        error_console.print(f"[red]Query failed:[/] {exc}")
        return 1
    return print_result(result, output_format, output, force)


def confirm_run() -> bool:
    return bool(sys.stdin.isatty() and Confirm.ask("Run this read-only query?", default=False))


def show_models() -> int:
    try:
        models = ollama_models()
    except Exception as exc:
        error_console.print(f"[red]Could not reach Ollama:[/] {exc}")
        return 1
    table = Table(title="Ollama models")
    table.add_column("name")
    table.add_column("size", justify="right")
    for model in models:
        table.add_row(str(model.get("name", "")), format_size(int(model.get("size", 0))))
    console.print(table)
    return 0


def show_schema(db_url: str) -> int:
    db_url = create_demo_db() if db_url == "demo" else db_url
    try:
        tables = inspect(db_url)
    except Exception as exc:
        error_console.print(f"[red]Could not inspect schema:[/] {exc}")
        return 1
    table = Table(title="Schema")
    table.add_column("table", style="cyan")
    table.add_column("column")
    table.add_column("type", style="green")
    table.add_column("key")
    for table_name, columns in tables.items():
        for index, (name, kind, primary_key) in enumerate(columns):
            table.add_row(table_name if index == 0 else "", name, kind or "-", "pk" if primary_key else "")
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
