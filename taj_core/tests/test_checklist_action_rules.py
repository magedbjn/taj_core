from datetime import datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "checklist" / "action_rules.py"


class TestChecklistActionRules(unittest.TestCase):
    def test_action_rules_module_exists(self):
        self.assertTrue(RULES_PATH.exists(), "Checklist action rules module is required")

    def _rules(self):
        namespace = {}
        exec(RULES_PATH.read_text(encoding="utf-8"), namespace)
        return namespace

    def test_issue_key_is_stable_and_scoped(self):
        rules = self._rules()
        build = rules["build_issue_key"]
        first = build("Retort Sterilizer Maintenance", "Q-0001", "Production", "")
        same = build("Retort Sterilizer Maintenance", "Q-0001", "Production", "")
        other_template = build("Mini Retort Maintenance", "Q-0001", "Production", "")
        other_location = build("Retort Sterilizer Maintenance", "Q-0001", "Warehouse", "")
        self.assertEqual(first, same)
        self.assertNotEqual(first, other_template)
        self.assertNotEqual(first, other_location)
        self.assertLessEqual(len(first), 140)

        # Blank Asset must preserve the legacy four-part key, while a real Asset
        # separates two physical machines that share one template/question.
        blank_asset = build("Retort Sterilizer Maintenance", "Q-0001", "Production", "", asset=None)
        asset_a = build("Retort Sterilizer Maintenance", "Q-0001", "Production", "", asset="ASSET-RETORT-01")
        asset_b = build("Retort Sterilizer Maintenance", "Q-0001", "Production", "", asset="ASSET-RETORT-02")
        self.assertEqual(first, blank_asset)
        self.assertNotEqual(asset_a, asset_b)
        self.assertNotEqual(first, asset_a)

    def test_observation_effect_encodes_recurrence_and_pass_behavior(self):
        rules = self._rules()
        effect = rules["observation_effect"]
        self.assertEqual(effect(True, True, False), "create_issue_action")
        self.assertEqual(effect(True, True, True), "append_issue")
        self.assertEqual(effect(False, True, True), "append_pass")
        self.assertEqual(effect(False, False, True), "append_pass")
        self.assertEqual(effect(True, False, False), "none")
        self.assertEqual(effect(False, True, False), "none")

    def test_resolution_and_overdue_rules(self):
        rules = self._rules()
        self.assertEqual(rules["next_resolution_status"](True), "Pending Verification")
        self.assertEqual(rules["next_resolution_status"](False), "Closed")
        for status in ("Open", "In Progress", "Waiting", "Pending Verification"):
            self.assertTrue(rules["is_open_action_status"](status))
        self.assertFalse(rules["is_open_action_status"]("Closed"))

        now = datetime(2026, 9, 15, 20, 0, 0)
        self.assertTrue(rules["action_is_overdue"]("Open", now - timedelta(minutes=1), now))
        self.assertFalse(rules["action_is_overdue"]("Closed", now - timedelta(days=1), now))
        self.assertFalse(rules["action_is_overdue"]("Open", now + timedelta(minutes=1), now))
        self.assertFalse(rules["action_is_overdue"]("Open", None, now))


if __name__ == "__main__":
    unittest.main()
