from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Label, ListItem, ListView, Static, TextArea, Tree

from asksql.adapters import adapter_for
from asksql.models import CancellationToken, ConnectionProfile, ExecutionStatus, QueryExecution, QueryResult
from asksql.service import QueryService
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, quote_identifier


class ConnectionListItem(ListItem):
    def __init__(self, profile: ConnectionProfile) -> None:
        super().__init__(Label(f"{profile.name}  [dim]{profile.url}[/]"))
        self.profile = profile


class ConnectionPickerApp(App[str | None]):
    TITLE = "asksql connections"
    BINDINGS = [("escape", "quit", "Cancel"), ("ctrl+q", "quit", "Cancel")]

    def __init__(self, profiles: list[ConnectionProfile]) -> None:
        super().__init__()
        self.profiles = profiles

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Select a database connection", id="connection-picker-title")
        yield ListView(*(ConnectionListItem(profile) for profile in self.profiles), id="connections")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#connections", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ConnectionListItem):
            self.exit(event.item.profile.url)


class AskSqlApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #top {
        height: 58%;
    }

    #bottom {
        height: 1fr;
    }

    #main {
        height: 1fr;
    }

    #schema {
        width: 34;
        border: solid $primary;
    }

    #work {
        width: 1fr;
    }

    #question {
        border: solid $accent;
        height: 3;
    }

    #sql {
        border: solid $success;
        height: 1fr;
    }

    #status {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    #results {
        height: 1fr;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+enter", "run_editor_sql", "Run SQL"),
        ("tab", "focus_next", "Next pane"),
        ("shift+tab", "focus_previous", "Previous pane"),
        ("f2", "focus_ask", "Ask AI"),
        ("f3", "focus_sql", "Edit SQL"),
        ("f5", "run_editor_sql", "Run SQL"),
        ("ctrl+c", "cancel_query", "Cancel query"),
        ("ctrl+r", "refresh_schema", "Refresh schema"),
    ]

    def __init__(self, db_url: str, model: str, limit: int = DEFAULT_LIMIT, timeout: float = DEFAULT_TIMEOUT) -> None:
        super().__init__()
        self.db_url = db_url
        self.model = model
        self.limit = limit
        self.timeout = timeout
        self.service = QueryService(db_url, model)
        self._cancellation: CancellationToken | None = None
        self._execution_id = 0
        self._preview_id = 0
        self._generation_id = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Horizontal(id="top"):
                yield Tree("Schema - select table to preview", id="schema")
                with Vertical(id="work"):
                    yield Input(placeholder="Ask AI - type a question, then press Enter", id="question")
                    yield TextArea("select * from customers limit 10", language="sql", id="sql")
                    yield Static(
                        "Tab/Shift+Tab move | Enter generates SQL | Ctrl+Enter runs SQL | Ctrl+Q quits", id="status"
                    )
            with Vertical(id="bottom"):
                yield DataTable(id="results")
        yield Footer()

    def on_mount(self) -> None:
        self._load_schema_tree()
        self.query_one("#sql", TextArea).focus()
        self._set_status("Ready - Tab to move, Ctrl+Enter to run SQL, Enter in Ask AI to generate SQL.")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if question:
            self.ask(question)

    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        if isinstance(event.node.data, str):
            self.preview(event.node.data)

    def action_refresh_schema(self) -> None:
        self._load_schema_tree()

    def action_focus_next(self) -> None:
        self.screen.focus_next()

    def action_focus_previous(self) -> None:
        self.screen.focus_previous()

    def action_focus_ask(self) -> None:
        self.query_one("#question", Input).focus()

    def action_focus_sql(self) -> None:
        self.query_one("#sql", TextArea).focus()

    def action_run_editor_sql(self) -> None:
        if self._cancellation:
            self._set_status("A query is already running. Press Ctrl+C to cancel it.")
            return
        self.run_sql(self.query_one("#sql", TextArea).text)

    def action_cancel_query(self) -> None:
        if not self._cancellation:
            self._set_status("No query is running.")
            return
        self._cancellation.cancel()
        self._set_status("Cancelling query...")

    def ask(self, question: str) -> None:
        if self._cancellation:
            self._set_status("A query is already running. Press Ctrl+C to cancel it.")
            return
        generation_id = self._next_generation_id()
        self._set_status(f"Asking {self.model}: {question}")
        self._ask(question, generation_id)

    @work(thread=True)
    def _ask(self, question: str, generation_id: int) -> None:
        try:
            sql = self.service.generate(question).sql
        except Exception as exc:
            self.call_from_thread(self._finish_generation, generation_id, None, str(exc))
            return
        self.call_from_thread(self._finish_generation, generation_id, sql, None)

    def _next_generation_id(self) -> int:
        self._generation_id += 1
        return self._generation_id

    def _finish_generation(self, generation_id: int, sql: str | None, error: str | None) -> None:
        if generation_id != self._generation_id:
            return
        if error:
            self._set_status(f"Error: {error}")
            return
        assert sql is not None
        self._set_sql(sql)
        self._set_status("Generated SQL. Review or edit it, then press Ctrl+Enter to run.")
        self.action_focus_sql()

    def run_sql(self, sql: str, source: str = "Manual SQL") -> None:
        cancellation = CancellationToken()
        execution_id = self._next_execution_id()
        self._cancellation = cancellation
        self._set_status(f"Running: {source}")
        self._execute_sql(sql, source, execution_id, cancellation)

    @work(thread=True)
    def _execute_sql(self, sql: str, source: str, execution_id: int, cancellation: CancellationToken) -> None:
        execution = self.service.execute(sql, limit=self.limit, timeout=self.timeout, cancellation=cancellation)
        self.call_from_thread(self._finish_sql, execution_id, cancellation, source, execution)

    def _next_execution_id(self) -> int:
        self._execution_id += 1
        return self._execution_id

    def _finish_sql(
        self, execution_id: int, cancellation: CancellationToken, source: str, execution: QueryExecution
    ) -> None:
        if execution_id != self._execution_id:
            return
        if self._cancellation is cancellation:
            self._cancellation = None
        if execution.status == ExecutionStatus.REFUSED:
            self._set_status(execution.error or "Refused non-read-only SQL.")
            return
        if execution.status == ExecutionStatus.TIMED_OUT:
            self._set_status(execution.error or "Query timed out.")
            return
        if execution.status == ExecutionStatus.CANCELLED:
            self._set_status("Query cancelled.")
            return
        if execution.status == ExecutionStatus.FAILED:
            self._set_status(f"Query failed: {execution.error}")
            return
        assert execution.result is not None
        assert isinstance(execution.result, QueryResult)
        columns, rows, truncated = execution.result.columns, execution.result.rows, execution.result.truncated
        suffix = f"row limit reached: {self.limit}" if truncated else f"{len(rows)} rows"
        self._set_status(f"{source} - {suffix}")
        self._set_results(columns, rows)

    def on_unmount(self) -> None:
        if self._cancellation:
            self._cancellation.cancel()

    def preview(self, table: str) -> None:
        if self._cancellation:
            self._set_status("A query is already running. Press Ctrl+C to cancel it.")
            return
        preview_id = self._next_preview_id()
        self._set_status(f"Previewing table: {table}")
        self._preview(table, preview_id)

    @work(thread=True)
    def _preview(self, table: str, preview_id: int) -> None:
        sql = f"select * from {quote_identifier(table)} limit 50"
        try:
            result = adapter_for(self.db_url).query(sql, 50, self.timeout, self._cancellation)
            columns, rows = result.columns, result.rows
        except Exception as exc:
            self.call_from_thread(self._finish_preview, preview_id, table, sql, None, None, str(exc))
            return
        self.call_from_thread(self._finish_preview, preview_id, table, sql, columns, rows, None)

    def _next_preview_id(self) -> int:
        self._preview_id += 1
        return self._preview_id

    def _finish_preview(
        self,
        preview_id: int,
        table: str,
        sql: str,
        columns: list[str] | None,
        rows: list[tuple[object, ...]] | None,
        error: str | None,
    ) -> None:
        if preview_id != self._preview_id or self._cancellation:
            return
        if error:
            self._set_status(f"Preview failed: {error}")
            return
        assert columns is not None and rows is not None
        self._set_sql(sql)
        self._set_status(f"Preview: {table} - {len(rows)} rows")
        self._set_results(columns, rows)

    def _load_schema_tree(self) -> None:
        tree = self.query_one("#schema", Tree)
        tree.clear()
        tree.root.label = "Schema"
        for table, table_schema in adapter_for(self.db_url).inspect_details().tables.items():
            table_node = tree.root.add(table, data=table)
            for column in table_schema.columns:
                foreign_key = next((fk for fk in table_schema.foreign_keys if fk.column == column.name), None)
                suffix = f" -> {foreign_key.referenced_table}.{foreign_key.referenced_column}" if foreign_key else ""
                table_node.add_leaf(
                    f"{column.name} {column.type}{' pk' if column.primary_key else ''}{suffix}".rstrip()
                )
        tree.root.expand()

    def _schema_text(self) -> str:
        lines = ["Schema", ""]
        for table, table_schema in adapter_for(self.db_url).inspect_details().tables.items():
            lines.append(table)
            for column in table_schema.columns:
                foreign_key = next((fk for fk in table_schema.foreign_keys if fk.column == column.name), None)
                suffix = f" -> {foreign_key.referenced_table}.{foreign_key.referenced_column}" if foreign_key else ""
                lines.append(f"  {column.name} {column.type}{' pk' if column.primary_key else ''}{suffix}".rstrip())
            lines.append("")
        return "\n".join(lines).strip()

    def _set_sql(self, sql: str) -> None:
        self.query_one("#sql", TextArea).load_text(sql)

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _set_results(self, columns: list[str], rows: list[tuple[object, ...]]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        for row in rows:
            table.add_row(*(str(value) for value in row))


def run_tui(db_url: str, model: str, limit: int = DEFAULT_LIMIT, timeout: float = DEFAULT_TIMEOUT) -> None:
    AskSqlApp(db_url, model, limit, timeout).run()


def pick_connection(profiles: list[ConnectionProfile]) -> str | None:
    return ConnectionPickerApp(profiles).run()
