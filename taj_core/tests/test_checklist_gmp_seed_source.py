from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
SEED_PATH = CHECKLIST / "gmp_seed.py"


class TestChecklistGmpSeedSource(unittest.TestCase):
    def test_seed_is_explicit_whitelisted_requires_manager_and_department(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn("@frappe.whitelist()", source)
        self.assertIn("def _ensure_seed_manager", source)
        self.assertIn("is_checklist_manager", source)
        self.assertIn("_ensure_seed_manager()", source)
        self.assertIn("def seed_gmp_checklists(department", source)
        self.assertIn('frappe.db.exists("Department", department)', source)
        self.assertIn("Department is required", source)

    def test_seed_does_not_commit_manually(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertNotIn("frappe.db.commit()", source)

    def test_seed_reuses_questions_by_exact_question_text(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn('frappe.db.exists("Checklist Question", {"question": question_text})', source)
        self.assertIn('frappe.new_doc("Checklist Question")', source)
        self.assertIn('"Pass/Fail/NA"', source)
        self.assertIn("require_failure_reason", source)
        self.assertIn("require_follow_up", source)

    def test_seed_reuses_legacy_catalog_question_text_and_syncs_failure_scope(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn('definition.get("legacy_questions")', source)
        self.assertIn('doc.question = question_text', source)
        self.assertIn('"require_affected_item"', source)
        self.assertIn('"affected_item_options"', source)
        self.assertIn('"require_issue_type"', source)
        self.assertIn('"issue_type_options"', source)

    def test_seed_creates_standard_masters_and_merges_question_standard_rows(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn('frappe.db.exists("Checklist Standard", standard_name)', source)
        self.assertIn('frappe.new_doc("Checklist Standard")', source)
        self.assertIn('doc.append("standards"', source)
        self.assertIn('definition.get("standards")', source)
        self.assertIn('standard_names = sorted(STANDARD_DEFAULTS)', source)
        self.assertNotIn('doc.set("standards", [])', source)

    def test_seed_only_syncs_catalog_owned_gmp_templates(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn("GMP_TEMPLATES", source)
        self.assertIn('template_name.startswith("GMP - ")', source)
        self.assertNotIn("frappe.delete_doc", source)
        self.assertNotIn("DELETE FROM", source.upper())

    def test_gmp_seed_uses_schedule_docs_and_reports_only_inactive_schedules(self):
        source = SEED_PATH.read_text(encoding="utf-8")
        self.assertIn('schedule.schedule_type = "Weeks of Month"', source)
        self.assertIn('schedule.is_active = 0', source)
        self.assertIn('frappe.db.get_value("Checklist Schedule", schedule_name, "is_active")', source)
        self.assertNotIn('"schedules_inactive_until_activated": [legacy_schedule_name(name) for name in GMP_TEMPLATES]', source)

    def test_seed_is_not_registered_as_a_patch(self):
        patches = ROOT / "patches.txt"
        if patches.exists():
            self.assertNotIn("gmp_seed", patches.read_text(encoding="utf-8"))
        hooks = ROOT / "hooks.py"
        self.assertNotIn("seed_gmp_checklists", hooks.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
