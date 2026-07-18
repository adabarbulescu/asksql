import unittest
from unittest.mock import patch

from asksql.demo import create_demo_db
from asksql.sqlite import DEFAULT_LIMIT, preview_table
from asksql.tui import AskSqlApp


class TuiTest(unittest.IsolatedAsyncioTestCase):
    async def test_tui_mounts(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            self.assertIn("customers", app._schema_text())
            self.assertIn("customer_id INTEGER -> customers.id", app._schema_text())
            self.assertEqual(app.focused.id, "sql")
            await pilot.press("ctrl+q")

    async def test_tui_previews_table(self) -> None:
        db_url = create_demo_db()
        app = AskSqlApp(db_url, "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app._set_results(*preview_table(db_url, "customers", 1))
            await pilot.pause()
            table = app.query_one("#results")
            self.assertGreaterEqual(table.row_count, 1)

    async def test_tui_sets_editor_sql(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app._set_sql("select 1")
            await pilot.pause()
            editor = app.query_one("#sql")
            self.assertEqual(editor.text, "select 1")

    async def test_tui_generates_sql_without_running_it(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        ran_sql = False

        def run_sql(*_: object) -> None:
            nonlocal ran_sql
            ran_sql = True

        app.run_sql = run_sql  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            with patch("asksql.tui.generate_sql", return_value="select * from customers"):
                app.ask("show customers")
                await pilot.pause(0.2)

            editor = app.query_one("#sql")
            self.assertEqual(editor.text, "select * from customers")
            self.assertFalse(ran_sql)

    async def test_tui_sets_status(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app._set_status("Manual SQL - 3 rows")
            await pilot.pause()
            self.assertIsNotNone(app.query_one("#status"))

    async def test_tui_stores_configured_limit(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b", limit=1)

        self.assertEqual(app.limit, 1)

    async def test_tui_default_limit(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")

        self.assertEqual(app.limit, DEFAULT_LIMIT)

    async def test_tui_focus_actions(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app.action_focus_ask()
            await pilot.pause()
            self.assertEqual(app.focused.id, "question")
            app.action_focus_sql()
            await pilot.pause()
            self.assertEqual(app.focused.id, "sql")


if __name__ == "__main__":
    unittest.main()
