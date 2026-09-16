from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe


class TestChecklistClaimPermissionsRuntime(TestCase):
    def test_same_department_user_gets_already_claimed_message(self):
        from taj_core.checklist import api as module

        current_user = "current@example.com"
        other_user = "other@example.com"
        doc = SimpleNamespace(
            docstatus=0,
            status="Expired",
            assignment_type="Any User in Department",
            assigned_user=None,
            department="Warehouse - Taj",
            taken_by=other_user,
        )

        with patch.object(
            module.frappe,
            "session",
            SimpleNamespace(user=current_user),
        ), patch.object(
            module.frappe,
            "get_doc",
            return_value=doc,
        ), patch.object(
            module,
            "is_checklist_manager",
            return_value=False,
        ), patch.object(
            module,
            "checklist_user_belongs_to_department",
            return_value=True,
        ):
            with self.assertRaisesRegex(
                frappe.PermissionError,
                "already been claimed by other@example.com",
            ):
                module.claim_checklist_answer("CHK-TEST")

    def test_wrong_department_still_gets_department_message(self):
        from taj_core.checklist import api as module

        current_user = "current@example.com"
        doc = SimpleNamespace(
            docstatus=0,
            status="Open",
            assignment_type="Any User in Department",
            assigned_user=None,
            department="Warehouse - Taj",
            taken_by=None,
        )

        with patch.object(
            module.frappe,
            "session",
            SimpleNamespace(user=current_user),
        ), patch.object(
            module.frappe,
            "get_doc",
            return_value=doc,
        ), patch.object(
            module,
            "is_checklist_manager",
            return_value=False,
        ), patch.object(
            module,
            "checklist_user_belongs_to_department",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                frappe.PermissionError,
                "do not belong to the department",
            ):
                module.claim_checklist_answer("CHK-TEST")


if __name__ == "__main__":
    import unittest
    unittest.main()
