from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "checklist" / "api.py"
USER_JS = ROOT / "checklist" / "page" / "checklist_user" / "checklist_user.js"


class TestChecklistOpenActionWarningSource(unittest.TestCase):
    def test_serialized_questions_include_existing_open_action(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("def _get_open_actions_for_answer", source)
        self.assertIn("build_issue_key", source)
        self.assertIn('"open_action"', source)
        self.assertIn('"open_action_status"', source)
        self.assertIn('"open_action_latest_observation"', source)

    def test_execution_ui_warns_that_pass_does_not_close_existing_action(self):
        source = USER_JS.read_text(encoding="utf-8")
        self.assertIn("open_action", source)
        self.assertIn("Open Action", source)
        self.assertIn("does not close", source)
        self.assertIn("open-action-warning", source)


if __name__ == "__main__":
    unittest.main()
