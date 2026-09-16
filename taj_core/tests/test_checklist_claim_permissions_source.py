from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"


class TestChecklistClaimPermissionsSource(unittest.TestCase):
    def test_claim_checks_department_membership_separately_from_taken_by(self):
        permissions = (CHECKLIST / "permissions.py").read_text(encoding="utf-8")
        api = (CHECKLIST / "api.py").read_text(encoding="utf-8")

        self.assertIn("def checklist_user_belongs_to_department", permissions)
        self.assertIn("checklist_user_belongs_to_department", api)

        start = api.index("def claim_checklist_answer")
        end = api.find("\n@frappe.whitelist()", start + 1)
        claim_source = api[start:] if end == -1 else api[start:end]

        self.assertNotIn(
            'checklist_answer_has_permission(doc, user, "write")',
            claim_source,
        )

        department_check = claim_source.index("checklist_user_belongs_to_department")
        claimed_check = claim_source.index("This checklist has already been claimed by")
        self.assertLess(department_check, claimed_check)


if __name__ == "__main__":
    unittest.main()
