from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "checklist" / "doctype" / "checklist_action" / "checklist_action.js"


class TestChecklistActionFormSource(unittest.TestCase):
    def test_action_form_exposes_lifecycle_buttons(self):
        source = JS.read_text(encoding="utf-8")
        for label in ("Start Action", "Set Waiting", "Submit Resolution", "Verify Resolution", "Reject Resolution"):
            self.assertIn(label, source)
        for method in ("start_action", "set_waiting", "submit_resolution", "verify_resolution"):
            self.assertIn(method, source)
        self.assertIn("Pending Verification", source)
        self.assertIn("resolution_details", source)


if __name__ == "__main__":
    unittest.main()
