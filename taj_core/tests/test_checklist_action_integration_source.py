from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
ACTIONS_PATH = CHECKLIST / "actions.py"
ANSWER_PATH = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py"
NOTIFICATIONS_PATH = CHECKLIST / "notifications.py"


class TestChecklistActionIntegrationSource(unittest.TestCase):
    def test_actions_service_encodes_create_reuse_and_pass_observation(self):
        self.assertTrue(ACTIONS_PATH.exists(), "Checklist actions service is required")
        source = ACTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn("def process_checklist_actions", source)
        self.assertIn("build_issue_key", source)
        self.assertIn("observation_effect", source)
        self.assertIn('"open_issue_key"', source)
        self.assertIn('"Issue"', source)
        self.assertIn('"Pass Observation"', source)
        self.assertIn("checklist_action", source)
        self.assertIn("occurrence_count", source)
        self.assertIn("Pending Verification", source)

    def test_unrouted_follow_up_defaults_to_checklist_department(self):
        source = ACTIONS_PATH.read_text(encoding="utf-8")
        self.assertIn('getattr(row, "responsible_department", None) or getattr(doc, "department", None)', source)

    def test_submit_processes_actions_before_legacy_issue_notifications(self):
        source = ANSWER_PATH.read_text(encoding="utf-8")
        start = source.index("    def on_submit(self):")
        end = source.index("    def validate_creator", start)
        block = source[start:end]
        self.assertIn("process_checklist_actions", block)
        self.assertIn("notify_checklist_issues", block)
        self.assertLess(block.index("process_checklist_actions"), block.index("notify_checklist_issues"))

    def test_legacy_notification_skips_follow_up_rows(self):
        source = NOTIFICATIONS_PATH.read_text(encoding="utf-8")
        start = source.index("def notify_checklist_issues")
        block = source[start:]
        self.assertIn("require_follow_up", block)
        self.assertIn("continue", block)


if __name__ == "__main__":
    unittest.main()
