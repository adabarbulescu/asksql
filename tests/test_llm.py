import os
import unittest
from unittest.mock import MagicMock, patch

from asksql.llm import check_model


class ModelCheckTest(unittest.TestCase):
    def test_checks_installed_ollama_model_and_latest_alias(self) -> None:
        with patch("asksql.llm.ollama_models", return_value=[{"name": "qwen:latest"}]):
            self.assertEqual(check_model("ollama:qwen"), (True, "Ollama is ready with qwen."))

    def test_reports_missing_ollama_model(self) -> None:
        with patch("asksql.llm.ollama_models", return_value=[{"name": "other:latest"}]):
            ready, detail = check_model("ollama:qwen")

        self.assertFalse(ready)
        self.assertIn("not installed", detail)

    def test_openai_check_requires_configured_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            ready, detail = check_model("openai:gpt-test")

        self.assertFalse(ready)
        self.assertIn("OPENAI_API_KEY", detail)

    def test_openai_check_uses_non_generation_models_endpoint(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "OPENAI_BASE_URL": "https://models.test/v1"}):
            with patch("asksql.llm.urllib.request.urlopen", return_value=response) as open_url:
                ready, _ = check_model("openai:gpt/test")

        self.assertTrue(ready)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://models.test/v1/models/gpt%2Ftest")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def test_rejects_malformed_or_unsupported_model(self) -> None:
        self.assertFalse(check_model("qwen")[0])
        self.assertFalse(check_model("other:qwen")[0])


if __name__ == "__main__":
    unittest.main()
