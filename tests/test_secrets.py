import sys
import unittest
from unittest.mock import MagicMock, patch

from asksql.secrets import get_secret, set_secret


class SecretStoreTest(unittest.TestCase):
    def test_environment_has_priority(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "environment"}):
            self.assertEqual(get_secret("OPENAI_API_KEY"), "environment")

    def test_uses_operating_system_keyring(self) -> None:
        keyring = MagicMock()
        keyring.get_password.return_value = "stored"
        with patch.dict(sys.modules, {"keyring": keyring}):
            self.assertEqual(get_secret("OPENAI_API_KEY"), "stored")
            set_secret("OPENAI_API_KEY", "new")

        keyring.set_password.assert_called_once_with("asksql", "OPENAI_API_KEY", "new")

    def test_refuses_unknown_secret_names(self) -> None:
        with self.assertRaises(ValueError):
            set_secret("OTHER", "value")


if __name__ == "__main__":
    unittest.main()
