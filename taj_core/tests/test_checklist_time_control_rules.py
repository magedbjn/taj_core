from datetime import datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "checklist" / "rules.py"


class TestChecklistTimeControlRules(unittest.TestCase):
    def _rules(self):
        namespace = {}
        exec(RULES_PATH.read_text(encoding="utf-8"), namespace)
        return namespace

    def test_scheduled_start_lock_only_applies_before_start(self):
        rules = self._rules()
        locked = rules["is_before_scheduled_start"]
        start = datetime(2026, 9, 16, 9, 0, 0)

        self.assertTrue(locked(start, start - timedelta(seconds=1)))
        self.assertFalse(locked(start, start))
        self.assertFalse(locked(start, start + timedelta(minutes=1)))
        self.assertFalse(locked(None, start - timedelta(hours=1)))


if __name__ == "__main__":
    unittest.main()
