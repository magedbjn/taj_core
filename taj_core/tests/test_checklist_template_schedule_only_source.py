from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_JS = ROOT / "checklist" / "doctype" / "checklist_question_template" / "checklist_question_template.js"
ADMIN_JS = ROOT / "checklist" / "page" / "checklist_admin" / "checklist_admin.js"
API = ROOT / "checklist" / "api.py"
TEMPLATE_PY = ROOT / "checklist" / "doctype" / "checklist_question_template" / "checklist_question_template.py"
ANSWER_PY = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.py"


class TestChecklistTemplateScheduleOnlySource(unittest.TestCase):
    def test_template_form_only_offers_schedule_management(self):
        source = TEMPLATE_JS.read_text(encoding="utf-8")
        self.assertIn('__("New Schedule")', source)
        self.assertIn('__("View Schedules")', source)
        self.assertNotIn('__("Create Checklist Answer")', source)
        self.assertNotIn("taj_core.checklist.api.create_checklist_answer", source)

    def test_admin_create_control_routes_to_schedules_instead_of_template_api(self):
        source = ADMIN_JS.read_text(encoding="utf-8")
        self.assertNotIn("taj_core.checklist.api.create_checklist_answer", source)
        self.assertIn('frappe.set_route("List", "Checklist Schedule"', source)

    def test_legacy_template_api_blocks_bypass_when_schedule_architecture_exists(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("Use Checklist Schedule", source)
        self.assertIn('frappe.db.exists("DocType", "Checklist Schedule")', source)
        self.assertNotIn('frappe.db.exists("Checklist Schedule", {"template": template_name})', source)

    def test_legacy_template_controller_endpoint_also_blocks_schedule_bypass(self):
        source = TEMPLATE_PY.read_text(encoding="utf-8")
        self.assertIn("Use Checklist Schedule", source)
        self.assertIn('frappe.db.exists("DocType", "Checklist Schedule")', source)

    def test_new_answer_form_cannot_bypass_schedule_architecture(self):
        source = ANSWER_PY.read_text(encoding="utf-8")
        self.assertIn("Create the checklist through Checklist Schedule", source)
        self.assertIn('not getattr(self, "schedule", None)', source)


if __name__ == "__main__":
    unittest.main()
