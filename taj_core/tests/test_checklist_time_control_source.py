from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
ANSWER_CONTROLLER = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py"
API = CHECKLIST / "api.py"
USER_JS = CHECKLIST / "page" / "checklist_user" / "checklist_user.js"
HOOKS = ROOT / "hooks.py"


class TestChecklistTimeControlSource(unittest.TestCase):
    def test_server_blocks_activity_before_scheduled_start(self):
        source = ANSWER_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("is_before_scheduled_start", source)
        self.assertIn("Checklist cannot be started before its scheduled start time", source)
        self.assertIn("validate_scheduled_start_reached(self)", source)

    def test_api_exposes_time_lock_and_ui_disables_early_editing(self):
        api = API.read_text(encoding="utf-8")
        ui = USER_JS.read_text(encoding="utf-8")
        self.assertIn('"is_time_locked"', api)
        self.assertIn("is_time_locked", ui)
        self.assertIn("Scheduled start", ui)

    def test_deadline_processing_runs_every_four_hours(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        self.assertIn('"0 */4 * * *"', hooks)
        self.assertNotIn('"*/5 * * * *"', hooks)
        self.assertNotIn('"hourly": [\n        "taj_core.checklist.scheduler.process_open_checklist_deadlines"', hooks)


if __name__ == "__main__":
    unittest.main()
