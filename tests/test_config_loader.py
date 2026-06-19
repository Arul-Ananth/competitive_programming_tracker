import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, "src")

from config_loader import load_config  # noqa: E402


class ConfigLoaderTests(unittest.TestCase):
    def test_notification_email_is_optional(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "sheet_url": "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
                        "timezone": "Asia/Kolkata",
                        "leetcode": "demo-user",
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(str(path))

        self.assertEqual(config.notification_email, "")

    def test_notification_email_is_preserved_when_present(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "sheet_url": "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
                        "timezone": "Asia/Kolkata",
                        "notification_email": "user@example.com",
                        "leetcode": "demo-user",
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(str(path))

        self.assertEqual(config.notification_email, "user@example.com")


if __name__ == "__main__":
    unittest.main()
