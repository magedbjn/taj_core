from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "checklist" / "engineering_maintenance_seed.py"


class EngineeringMaintenanceSeedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SEED.read_text(encoding="utf-8")

    def test_destructive_command_requires_explicit_confirmation(self):
        self.assertIn('CONFIRMATION_PHRASE = "DELETE ALL CHECKLIST DATA"', self.source)
        self.assertIn("if confirm != CONFIRMATION_PHRASE:", self.source)
        guard = self.source.index("if confirm != CONFIRMATION_PHRASE:")
        delete_call = self.source.index("_delete_parent_docs(")
        self.assertLess(guard, delete_call)

    def test_department_is_validated_before_any_delete(self):
        self.assertIn('TARGET_DEPARTMENT = "Maintenance - Taj"', self.source)
        exists_check = self.source.index('frappe.db.exists("Department", TARGET_DEPARTMENT)')
        delete_call = self.source.index("_delete_parent_docs(")
        self.assertLess(exists_check, delete_call)

    def test_requested_parent_doctypes_are_deleted_in_dependency_order(self):
        self.assertIn(
            'RESET_DOCTYPES = ("Checklist Answer", "Checklist Question Template", "Checklist Question")',
            self.source,
        )
        self.assertIn("frappe.delete_doc(", self.source)
        self.assertIn("force=1", self.source)
        self.assertIn("ignore_permissions=True", self.source)


    def test_submitted_answers_are_cancelled_before_delete(self):
        self.assertIn("if doc.docstatus == 1:", self.source)
        self.assertIn("doc.flags.ignore_permissions = True", self.source)
        self.assertIn("doc.flags.ignore_links = True", self.source)
        cancel = self.source.index("doc.cancel()")
        delete = self.source.index("frappe.delete_doc(")
        self.assertLess(cancel, delete)

    def test_seed_templates_are_manual_and_department_assigned(self):
        self.assertIn('"department": TARGET_DEPARTMENT', self.source)
        self.assertIn('"assignment_type": "Any User in Department"', self.source)
        self.assertIn('"periodicity": "None"', self.source)
        self.assertIn('"cycle_behavior": "Fresh Every Cycle"', self.source)

    def test_questions_are_created_once_then_reused_by_templates(self):
        self.assertIn("question_names = _create_questions()", self.source)
        self.assertIn('question_names[key]', self.source)
        self.assertIn('doc.append("questions", {"question": question_names[key]})', self.source)

    def test_commit_happens_once_after_all_creation(self):
        self.assertEqual(self.source.count("frappe.db.commit()"), 1)
        commit = self.source.index("frappe.db.commit()")
        create_templates = self.source.index("created_templates = _create_templates(question_names)")
        self.assertGreater(commit, create_templates)

    def test_seed_is_not_exposed_as_whitelisted_http_method(self):
        self.assertNotIn("@frappe.whitelist", self.source)


if __name__ == "__main__":
    unittest.main()
