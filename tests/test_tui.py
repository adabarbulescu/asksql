import unittest

from asksql.demo import create_demo_db
from asksql.sqlite import preview_table
from asksql.tui import AskSqlApp


class TuiTest(unittest.IsolatedAsyncioTestCase):
    async def test_tui_mounts(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            self.assertIn("customers", app._schema_text())
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


if __name__ == "__main__":
    unittest.main()
