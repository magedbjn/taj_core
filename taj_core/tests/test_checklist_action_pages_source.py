from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
API = CHECKLIST / "api.py"
TODAY = CHECKLIST / "page" / "checklist_today" / "checklist_today.js"
CONTROL = CHECKLIST / "page" / "checklist_control_room" / "checklist_control_room.js"


class TestChecklistActionPagesSource(unittest.TestCase):
    def test_today_api_returns_my_actions_and_action_summary(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("def _get_open_action_rows", source)
        self.assertIn("def _build_action_summary", source)
        start = source.index("def get_checklist_today_data")
        end = source.index("def get_checklist_control_room_data", start)
        block = source[start:end]
        self.assertIn('"my_actions"', block)
        self.assertIn('"action_summary"', block)

    def test_control_room_api_returns_action_kpis_and_rows(self):
        source = API.read_text(encoding="utf-8")
        start = source.index("def get_checklist_control_room_data")
        block = source[start:]
        self.assertIn('"actions"', block)
        self.assertIn('"action_summary"', block)
        self.assertIn("pending_verification", source)

    def test_today_page_has_my_actions_tab_and_action_cards(self):
        source = TODAY.read_text(encoding="utf-8")
        self.assertIn('data-tab="actions"', source)
        self.assertIn("My Actions", source)
        self.assertIn("render_action_rows", source)
        self.assertIn('frappe.set_route("Form", "Checklist Action"', source)

    def test_control_room_has_action_kpis_and_open_action_panel(self):
        source = CONTROL.read_text(encoding="utf-8")
        for label in ("Open Actions", "Action Overdue", "Action Critical", "Pending Verification"):
            self.assertIn(label, source)
        self.assertIn("render_actions", source)
        self.assertIn('data-action-name', source)


if __name__ == "__main__":
    unittest.main()
