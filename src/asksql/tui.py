from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Label, Static

from asksql.llm import generate_sql
from asksql.safety import is_read_only
from asksql.sqlite import inspect, query, schema


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
        padding: 0 1;
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
        height: 9;
        padding: 0 1;
    }

    #results {
        height: 1fr;
    }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, db_url: str, model: str) -> None:
        super().__init__()
        self.db_url = db_url
        self.model = model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            yield Static(self._schema_text(), id="schema")
            with Vertical(id="work"):
                yield Input(placeholder="Ask a question, then press Enter", id="question")
                yield Static("Generated SQL will appear here.", id="sql")
                yield DataTable(id="results")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#question", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if question:
            self.ask(question)

    @work(thread=True)
    def ask(self, question: str) -> None:
        self.call_from_thread(self._set_sql, f"Asking {self.model}...")
        try:
            sql = generate_sql(self.model, schema(self.db_url), question)
            if not is_read_only(sql):
                self.call_from_thread(self._set_sql, f"Refusing non-read-only SQL:\n\n{sql}")
                return
            columns, rows = query(self.db_url, sql)
        except Exception as exc:
            self.call_from_thread(self._set_sql, f"Error: {exc}")
            return
        self.call_from_thread(self._set_sql, sql)
        self.call_from_thread(self._set_results, columns, rows)

    def _schema_text(self) -> str:
        lines = ["Schema", ""]
        for table, columns in inspect(self.db_url).items():
            lines.append(table)
            lines.extend(f"  {name} {kind}{' pk' if primary_key else ''}".rstrip() for name, kind, primary_key in columns)
            lines.append("")
        return "\n".join(lines).strip()

    def _set_sql(self, sql: str) -> None:
        self.query_one("#sql", Static).update(sql)

    def _set_results(self, columns: list[str], rows: list[tuple[object, ...]]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        for row in rows:
            table.add_row(*(str(value) for value in row))


def run_tui(db_url: str, model: str) -> None:
    AskSqlApp(db_url, model).run()
