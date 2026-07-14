import unittest

from asksql.demo import create_demo_db
from asksql.tui import AskSqlApp


class TuiTest(unittest.IsolatedAsyncioTestCase):
    async def test_tui_mounts(self) -> None:
        app = AskSqlApp(create_demo_db(), "ollama:qwen2.5-coder:7b")
        async with app.run_test() as pilot:
            self.assertIn("customers", app._schema_text())
            await pilot.press("ctrl+q")


if __name__ == "__main__":
    unittest.main()
