import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "see" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import usage_log


class UsageLogTests(unittest.TestCase):
    def test_append_read_clear_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="see-log-") as tmp:
            log_path = Path(tmp) / "usage.log"
            with patch.dict(os.environ, {"SEE_LOG_FILE": str(log_path)}, clear=False):
                usage_log.append("analyze_success", kind="image", count=2)
                entries = usage_log.read(200)
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["event"], "analyze_success")
                self.assertEqual(entries[0]["count"], 2)
                self.assertTrue(usage_log.clear())
                self.assertEqual(usage_log.read(200), [])
                self.assertFalse(usage_log.clear())

    def test_append_redacts_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="see-log-") as tmp:
            log_path = Path(tmp) / "usage.log"
            with patch.dict(os.environ, {"SEE_LOG_FILE": str(log_path)}, clear=False):
                usage_log.append(
                    "analyze_failed",
                    api_key="sk-very-secret",
                    error="HTTP 401 Authorization: Bearer sk-very-secret",
                    provider="custom",
                )
            content = log_path.read_text(encoding="utf-8")
            self.assertNotIn("sk-very-secret", content)
            self.assertIn('"provider": "custom"', content)
            self.assertIn('"error":', content)

    def test_append_caps_line_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="see-log-") as tmp:
            log_path = Path(tmp) / "usage.log"
            with patch.dict(os.environ, {"SEE_LOG_FILE": str(log_path)}, clear=False):
                with patch.object(usage_log, "MAX_LINES", 3):
                    for index in range(10):
                        usage_log.append("run", index=index)
                    entries = usage_log.read(200)
            self.assertEqual(len(entries), 3)
            self.assertEqual(entries[0]["index"], 7)


if __name__ == "__main__":
    unittest.main()
