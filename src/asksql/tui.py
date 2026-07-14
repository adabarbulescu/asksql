from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static, TextArea, Tree

from asksql.llm import generate_sql
from asksql.safety import is_read_only
from asksql.sqlite import inspect, preview_table, query, quote_identifier, schema


class AskSqlApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
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
        height: 10;
    }

    #results {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+r", "refresh_schema", "Refresh schema"),
        ("ctrl+enter", "run_editor_sql", "Run SQL"),
    ]

    def __init__(self, db_url: str, model: str) -> None:
        super().__init__()
        self.db_url = db_url
        self.model = model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            yield Tree("Schema", id="schema")
            with Vertical(id="work"):
                yield Input(placeholder="Ask a question, then press Enter", id="question")
                yield TextArea("select * from customers limit 10", language="sql", id="sql")
                yield DataTable(id="results")
        yield Footer()

    def on_mount(self) -> None:
        self._load_schema_tree()
        self.query_one("#question", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if question:
            self.ask(question)

    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        if isinstance(event.node.data, str):
            self.preview(event.node.data)

    def action_refresh_schema(self) -> None:
        self._load_schema_tree()

    def action_run_editor_sql(self) -> None:
        self.run_sql(self.query_one("#sql", TextArea).text)

    @work(thread=True)
    def ask(self, question: str) -> None:
        self.call_from_thread(self._set_sql, f"-- Asking {self.model}...")
        try:
            sql = generate_sql(self.model, schema(self.db_url), question)
            if not is_read_only(sql):
                self.call_from_thread(self._set_sql, f"Refusing non-read-only SQL:\n\n{sql}")
                return
        except Exception as exc:
            self.call_from_thread(self._set_sql, f"Error: {exc}")
            return
        self.call_from_thread(self._set_sql, sql)
        self.run_sql(sql)

    @work(thread=True)
    def run_sql(self, sql: str) -> None:
        if not is_read_only(sql):
            self.call_from_thread(self._set_sql, f"Refusing non-read-only SQL:\n\n{sql}")
            return
        try:
            columns, rows = query(self.db_url, sql)
        except Exception as exc:
            self.call_from_thread(self._set_sql, f"Error: {exc}")
            return
        self.call_from_thread(self._set_results, columns, rows)

    @work(thread=True)
    def preview(self, table: str) -> None:
        sql = f"select * from {quote_identifier(table)} limit 50"
        self.call_from_thread(self._set_sql, sql)
        try:
            columns, rows = preview_table(self.db_url, table)
        except Exception as exc:
            self.call_from_thread(self._set_sql, f"Error: {exc}")
            return
        self.call_from_thread(self._set_results, columns, rows)

    def _load_schema_tree(self) -> None:
        tree = self.query_one("#schema", Tree)
        tree.clear()
        tree.root.label = "Schema"
        for table, columns in inspect(self.db_url).items():
            table_node = tree.root.add(table, data=table)
            for name, kind, primary_key in columns:
                table_node.add_leaf(f"{name} {kind}{' pk' if primary_key else ''}".rstrip())
        tree.root.expand()

    def _schema_text(self) -> str:
        lines = ["Schema", ""]
        for table, columns in inspect(self.db_url).items():
            lines.append(table)
            lines.extend(f"  {name} {kind}{' pk' if primary_key else ''}".rstrip() for name, kind, primary_key in columns)
            lines.append("")
        return "\n".join(lines).strip()

    def _set_sql(self, sql: str) -> None:
        self.query_one("#sql", TextArea).load_text(sql)

    def _set_results(self, columns: list[str], rows: list[tuple[object, ...]]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        for row in rows:
            table.add_row(*(str(value) for value in row))


def run_tui(db_url: str, model: str) -> None:
    AskSqlApp(db_url, model).run()
