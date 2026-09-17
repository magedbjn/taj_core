from pathlib import Path
import inspect
import unittest

from taj_core.checklist import rules

ROOT = Path(__file__).resolve().parents[1]
ANSWER_PY = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.py"


class TestChecklistManualScheduleCycles(unittest.TestCase):
    def test_manual_reuse_rule_reuses_only_continue_until_completed(self):
        helper = getattr(rules, "should_reuse_manual_open_checklist", None)
        self.assertIsNotNone(helper)
        self.assertFalse(helper("Fresh Every Cycle"))
        self.assertTrue(helper("Continue Until Completed"))

    def test_generation_key_supports_distinct_manual_cycle_tokens(self):
        signature = inspect.signature(rules.stable_generation_key)
        self.assertIn("cycle_token", signature.parameters)

        first = rules.stable_generation_key(
            "GMP - Receiving",
            "2026-09-17",
            schedule_name="GMP - Receiving - Manual Test",
            cycle_token="manual-run-1",
        )
        second = rules.stable_generation_key(
            "GMP - Receiving",
            "2026-09-17",
            schedule_name="GMP - Receiving - Manual Test",
            cycle_token="manual-run-2",
        )
        self.assertEqual(len(first), 64)
        self.assertEqual(len(second), 64)
        self.assertNotEqual(first, second)

    def test_schedule_creation_integrates_manual_cycle_behavior(self):
        source = ANSWER_PY.read_text(encoding="utf-8")
        self.assertIn("should_reuse_manual_open_checklist", source)
        self.assertIn("is_manual_schedule", source)
        self.assertIn("manual_cycle_token", source)
        self.assertIn("allow_parallel_manual_cycle", source)


if __name__ == "__main__":
    unittest.main()
