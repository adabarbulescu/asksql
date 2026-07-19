from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from asksql.demo import create_demo_db
from asksql.export import format_result
from asksql.llm import ollama_models
from asksql.models import ExecutionStatus, MutationResult, QueryExecution, QueryResult
from asksql.service import QueryService
from asksql.sql import pretty_sql
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, MAX_LIMIT, inspect, schema
from asksql.tui import run_tui

console = Console()
error_console = Console(stderr=True)
COMMANDS = {"ask", "run", "tui", "schema", "models"}
VALUE_OPTIONS = {"--model", "--format", "--output", "--limit", "--timeout"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_legacy_parser() if _is_legacy_ask(argv) else build_parser()
    args = parser.parse_args(argv)
    if not validate_output_options(args.format, args.output, args.force):
        return 1
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = base_parser()
    subparsers = parser.add_subparsers(dest="command")

    ask = subparsers.add_parser("ask", help="generate SQL from a question and optionally run it")
    ask.add_argument("database")
    ask.add_argument("question", nargs=argparse.REMAINDER)
    ask.set_defaults(func=command_ask)

    run = subparsers.add_parser("run", help="run read-only SQL or explicitly opted-in writes")
    run.add_argument("--write", action="store_true", help="allow one INSERT, UPDATE, DELETE, or DDL statement")
    run.add_argument("database")
    run.add_argument("sql", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    tui = subparsers.add_parser("tui", help="open the terminal UI")
    tui.add_argument("database", nargs="?", default="demo")
    tui.set_defaults(func=command_tui)

    schema_command = subparsers.add_parser("schema", help="show database schema")
    schema_command.add_argument("database", nargs="?", default="demo")
    schema_command.set_defaults(func=command_schema)

    models = subparsers.add_parser("models", help="list Ollama models")
    models.set_defaults(func=command_models)

    parser.set_defaults(func=command_help)
    return parser


def build_legacy_parser() -> argparse.ArgumentParser:
    parser = base_parser()
    parser.add_argument("database", nargs="?")
    parser.add_argument("question", nargs=argparse.REMAINDER)
    parser.set_defaults(func=command_ask)
    return parser


def base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask your database questions from the terminal.")
    parser.add_argument("--model", default="ollama:qwen2.5-coder:7b", help="ollama:name or openai:name")
    parser.add_argument("--dry-run", action="store_true", help="show SQL without running it")
    parser.add_argument(
        "--format", choices=["table", "csv", "json", "markdown"], default="table", help="result output format"
    )
    parser.add_argument("--output", help="write csv/json/markdown output to a file")
    parser.add_argument("--force", action="store_true", help="overwrite --output if it exists")
    parser.add_argument("--limit", type=result_limit, default=DEFAULT_LIMIT, help=f"maximum result rows, 1-{MAX_LIMIT}")
    parser.add_argument(
        "--timeout", type=query_timeout, default=DEFAULT_TIMEOUT, help="SQLite execution timeout in seconds"
    )
    parser.add_argument("-y", "--yes", action="store_true", help="run read-only SQL without prompting")
    parser.add_argument("--show-schema", action="store_true", help="print the schema sent to the model")
    return parser


def _is_legacy_ask(argv: list[str]) -> bool:
    first = _first_positional(argv)
    return bool(first and first not in COMMANDS)


def _first_positional(argv: list[str]) -> str | None:
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            return argv[index + 1] if index + 1 < len(argv) else None
        if arg in VALUE_OPTIONS:
            index += 2
            continue
        if any(arg.startswith(f"{option}=") for option in VALUE_OPTIONS):
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        return arg
    return None


def command_help(args: argparse.Namespace) -> int:
    build_parser().print_help()
    return 0


def command_models(args: argparse.Namespace) -> int:
    return show_models()


def command_schema(args: argparse.Namespace) -> int:
    return show_schema(args.database)


def command_tui(args: argparse.Namespace) -> int:
    run_tui(resolve_db_url(args.database), args.model, args.limit, args.timeout)
    return 0


def command_ask(args: argparse.Namespace) -> int:
    question = " ".join(args.question).strip()
    if not args.database or not question:
        build_parser().print_help()
        return 0

    db_url = resolve_db_url(args.database)
    service = QueryService(db_url, args.model)
    try:
        db_schema = schema(db_url)
        sql_console = console if args.format == "table" and not args.output else error_console
        if args.show_schema:
            sql_console.print(Panel(db_schema, title="Schema", border_style="blue"))
        with sql_console.status(f"Asking {args.model}...", spinner="dots"):
            sql = service.generate(question).sql
    except Exception as exc:
        error_console.print(f"[red]Error:[/] {exc}")
        return 1

    sql_console.print(Panel(Syntax(sql, "sql", theme="ansi_dark"), title="Generated SQL", border_style="green"))

    if args.dry_run:
        return 0
    if not args.yes and not confirm_run():
        return 1

    execution = service.execute(sql, limit=args.limit, timeout=args.timeout)
    if execution.status != ExecutionStatus.SUCCEEDED:
        return print_execution_error(execution)
    assert execution.result is not None
    assert isinstance(execution.result, QueryResult)
    return print_result(execution.result, args.format, args.output, args.force)


def command_run(args: argparse.Namespace) -> int:
    sql = " ".join(args.sql).strip()
    if not args.database or not sql:
        console.print('[red]Usage:[/] asksql run <db-url|demo> "select ..."')
        return 1
    if args.write and (args.output or args.format != "table"):
        error_console.print("[red]Write execution does not support --format or --output.[/]")
        return 1
    return run_sql(
        args.database,
        sql,
        args.yes,
        args.format,
        args.output,
        args.force,
        args.limit,
        args.timeout,
        allow_write=args.write,
    )


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
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            error_console.print(f"[red]Could not write output:[/] {exc}")
            return 1
        error_console.print(f"Wrote {output_format} to {path}")
    else:
        sys.stdout.write(text)
    if result.truncated:
        error_console.print(f"[yellow]Result row limit reached: {result.limit}.[/]")
    return 0


def print_execution_error(execution: QueryExecution) -> int:
    if execution.status == ExecutionStatus.REFUSED:
        error_console.print(f"[red]{execution.error}[/]")
        return 2
    if execution.status in {ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED}:
        error_console.print(f"[red]{execution.error}[/]")
        return 124 if execution.status == ExecutionStatus.TIMED_OUT else 130
    error_console.print(f"[red]Query failed:[/] {execution.error}")
    return 1


def validate_output_options(output_format: str, output: str | None = None, force: bool = False) -> bool:
    if output_format == "table" and output:
        error_console.print("[red]--output requires --format csv, json, or markdown.[/]")
        return False
    if force and not output:
        error_console.print("[red]--force requires --output.[/]")
        return False
    return True


def result_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if not 1 <= limit <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def query_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite number greater than 0")
    return timeout


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


def run_sql_command(
    text: str,
    yes: bool,
    output_format: str = "table",
    output: str | None = None,
    force: bool = False,
    limit: int = DEFAULT_LIMIT,
    timeout: float | None = DEFAULT_TIMEOUT,
    allow_write: bool = False,
) -> int:
    target, _, sql = text.partition(" ")
    if not target or not sql:
        console.print('[red]Usage:[/] asksql run <db-url|demo> "select ..."')
        return 1
    return run_sql(target, sql, yes, output_format, output, force, limit, timeout, allow_write=allow_write)


def run_sql(
    database: str,
    sql: str,
    yes: bool,
    output_format: str = "table",
    output: str | None = None,
    force: bool = False,
    limit: int = DEFAULT_LIMIT,
    timeout: float | None = DEFAULT_TIMEOUT,
    *,
    allow_write: bool = False,
) -> int:
    db_url = resolve_db_url(database)
    service = QueryService(db_url)
    sql = pretty_sql(sql)
    sql_console = console if output_format == "table" and not output else error_console
    sql_console.print(Panel(Syntax(sql, "sql", theme="ansi_dark"), title="SQL", border_style="green"))
    if not yes and not confirm_run(write=allow_write):
        return 1
    execution = service.execute(sql, limit=limit, timeout=timeout, allow_write=allow_write)
    if execution.status != ExecutionStatus.SUCCEEDED:
        return print_execution_error(execution)
    assert execution.result is not None
    if isinstance(execution.result, MutationResult):
        return print_mutation_result(execution.result)
    return print_result(execution.result, output_format, output, force)


def resolve_db_url(database: str) -> str:
    return create_demo_db() if database == "demo" else database


def print_mutation_result(result: MutationResult) -> int:
    noun = "row" if result.affected_rows == 1 else "rows"
    message = f"[green]Committed.[/] {result.affected_rows} {noun} affected."
    if result.last_insert_id is not None:
        message += f" Last insert id: {result.last_insert_id}."
    console.print(message)
    return 0


def confirm_run(*, write: bool = False) -> bool:
    prompt = "Commit this write statement?" if write else "Run this read-only query?"
    return bool(sys.stdin.isatty() and Confirm.ask(prompt, default=False))


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
        size = model.get("size", 0)
        table.add_row(str(model.get("name", "")), format_size(size if isinstance(size, int) else 0))
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
    for table_name, table_schema in tables.items():
        for index, column in enumerate(table_schema.columns):
            foreign_key = next((fk for fk in table_schema.foreign_keys if fk.column == column.name), None)
            key = "pk" if column.primary_key else ""
            if foreign_key:
                key = f"{key} references {foreign_key.referenced_table}.{foreign_key.referenced_column}".strip()
            table.add_row(table_name if index == 0 else "", column.name, column.type or "-", key)
    console.print(table)
    return 0


def format_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


if __name__ == "__main__":
    raise SystemExit(main())
