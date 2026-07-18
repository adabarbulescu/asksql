import unittest

from asksql.demo import create_demo_db
from asksql.models import CancellationToken, ExecutionStatus, QueryExecution, QueryResult
from asksql.sqlite import DEFAULT_LIMIT, DEFAULT_TIMEOUT, preview_table
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

    async def test_tui_uses_query_service(self) -> None:
        db_url = create_demo_db()
        app = AskSqlApp(db_url, "ollama:qwen2.5-coder:7b")

        self.assertEqual(app.service.db_url, db_url)
        self.assertEqual(app.service.model, "ollama:qwen2.5-coder:7b")

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

    async def test_tui_stores_timeout(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b", timeout=0.5)

        self.assertEqual(app.timeout, 0.5)

    async def test_tui_default_timeout(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")

        self.assertEqual(app.timeout, DEFAULT_TIMEOUT)

    async def test_tui_cancel_without_running_query(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app.action_cancel_query()
            await pilot.pause()
            self.assertIsNotNone(app.query_one("#status"))

    async def test_tui_does_not_bind_ctrl_z_to_cancel(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")

        self.assertNotIn("ctrl+z", {binding[0] for binding in app.BINDINGS})

    async def test_tui_blocks_second_run_while_query_active(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        token = CancellationToken()
        app._cancellation = token
        async with app.run_test() as pilot:
            app.action_run_editor_sql()
            await pilot.pause()

            self.assertIs(app._cancellation, token)

    async def test_tui_preview_during_query_does_not_change_results(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        token = CancellationToken()
        app._cancellation = token
        async with app.run_test() as pilot:
            app._set_sql("select 1")
            app._set_results(["value"], [(1,)])
            app.preview("customers")
            await pilot.pause()

            self.assertEqual(app.query_one("#sql").text, "select 1")
            self.assertEqual(app.query_one("#results").row_count, 1)
            self.assertIs(app._cancellation, token)

    async def test_tui_marks_query_active_before_worker_runs(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        calls = []

        def fake_execute(sql: str, source: str, execution_id: int, cancellation: CancellationToken) -> None:
            calls.append((sql, source, execution_id, cancellation))

        app._execute_sql = fake_execute  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            app.run_sql("select 1")
            await pilot.pause()

            self.assertIsNotNone(app._cancellation)
            self.assertEqual(app._execution_id, 1)
            self.assertEqual(calls[0][0], "select 1")
            self.assertIs(calls[0][3], app._cancellation)

    async def test_tui_keeps_latest_generation_when_responses_finish_out_of_order(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        calls = []

        def fake_ask(question: str, generation_id: int) -> None:
            calls.append((question, generation_id))

        app._ask = fake_ask  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            app.ask("old")
            app.ask("new")
            app._finish_generation(calls[1][1], "select 'new'", None)
            app._finish_generation(calls[0][1], "select 'old'", None)
            await pilot.pause()

            self.assertEqual(app.query_one("#sql").text, "select 'new'")

    async def test_tui_ignores_stale_execution_result(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app._execution_id = 2
            execution = QueryExecution(
                "select 1", QueryResult(["id"], [(1,)], False, 200), 0, ExecutionStatus.SUCCEEDED, None
            )
            app._finish_sql(1, CancellationToken(), "Manual SQL", execution)
            await pilot.pause()

            table = app.query_one("#results")
            self.assertEqual(table.row_count, 0)

    async def test_tui_ignores_stale_preview_after_newer_query(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            app._preview_id = 1
            app._cancellation = CancellationToken()
            app._set_sql("select 1")
            app._set_results(["value"], [(1,)])
            app._finish_preview(1, "customers", "select * from customers limit 50", ["id"], [(2,)], None)
            await pilot.pause()

            self.assertEqual(app.query_one("#sql").text, "select 1")
            self.assertEqual(app.query_one("#results").row_count, 1)

    async def test_tui_keeps_latest_preview_when_responses_finish_out_of_order(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        calls = []

        def fake_preview(table: str, preview_id: int) -> None:
            calls.append((table, preview_id))

        app._preview = fake_preview  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            app.preview("customers")
            app.preview("orders")
            app._finish_preview(calls[1][1], "orders", "select * from orders limit 50", ["id"], [(2,)], None)
            app._finish_preview(calls[0][1], "customers", "select * from customers limit 50", ["id"], [(1,)], None)
            await pilot.pause()

            self.assertEqual(app.query_one("#sql").text, "select * from orders limit 50")
            self.assertEqual(app.query_one("#results").row_count, 1)

    async def test_tui_unmount_cancels_running_query(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        token = CancellationToken()
        app._cancellation = token

        app.on_unmount()

        self.assertTrue(token.cancelled)

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
