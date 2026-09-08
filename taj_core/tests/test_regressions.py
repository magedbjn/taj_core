from unittest import TestCase
from unittest.mock import patch

from taj_core.company_documents.doctype.license.license import (
    get_license_status,
)
from taj_core.custom.expenses_claim import (
    _apply_transition_to_state,
)


class TestLicenseStatus(TestCase):
    def test_expired_before_today(self):
        self.assertEqual(
            get_license_status(-1, 30),
            "Expired",
        )

    def test_renew_window_is_inclusive(self):
        self.assertEqual(
            get_license_status(0, 30),
            "Renew",
        )
        self.assertEqual(
            get_license_status(30, 30),
            "Renew",
        )

    def test_active_after_renew_window(self):
        self.assertEqual(
            get_license_status(31, 30),
            "Active",
        )


class TestExpenseClaimWorkflowTransition(TestCase):
    @patch(
        "taj_core.custom.expenses_claim.apply_workflow"
    )
    @patch(
        "taj_core.custom.expenses_claim.get_transitions"
    )
    def test_uses_action_that_reaches_target_state(
        self,
        mock_get_transitions,
        mock_apply_workflow,
    ):
        claim = object()

        mock_get_transitions.return_value = [
            {
                "action": "Approve",
                "next_state": "Unpaid",
            },
            {
                "action": "Record Payment",
                "next_state": "Paid",
            },
        ]

        result = _apply_transition_to_state(
            claim,
            "Paid",
        )

        self.assertTrue(result)
        mock_apply_workflow.assert_called_once_with(
            claim,
            "Record Payment",
        )

    @patch(
        "taj_core.custom.expenses_claim.apply_workflow"
    )
    @patch(
        "taj_core.custom.expenses_claim.get_transitions"
    )
    def test_missing_transition_does_not_mutate_workflow(
        self,
        mock_get_transitions,
        mock_apply_workflow,
    ):
        claim = object()

        mock_get_transitions.return_value = [
            {
                "action": "Approve",
                "next_state": "Unpaid",
            },
        ]

        result = _apply_transition_to_state(
            claim,
            "Paid",
        )

        self.assertFalse(result)
        mock_apply_workflow.assert_not_called()

    @patch(
        "taj_core.custom.expenses_claim.apply_workflow"
    )
    @patch(
        "taj_core.custom.expenses_claim.get_transitions"
    )
    def test_workflow_failure_is_not_replaced_by_direct_update(
        self,
        mock_get_transitions,
        mock_apply_workflow,
    ):
        claim = object()

        mock_get_transitions.return_value = [
            {
                "action": "Paid",
                "next_state": "Paid",
            },
        ]

        mock_apply_workflow.side_effect = RuntimeError(
            "workflow blocked"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "workflow blocked",
        ):
            _apply_transition_to_state(
                claim,
                "Paid",
            )

        mock_apply_workflow.assert_called_once_with(
            claim,
            "Paid",
        )


class TestProductProposalWritePermissions(TestCase):
    def test_link_existing_item_requires_write_permission(self):
        import frappe
        from unittest.mock import Mock

        from taj_core.rnd.doctype.product_proposal.product_proposal import (
            ProductProposal,
        )

        proposal = Mock()
        proposal.check_permission.side_effect = frappe.PermissionError

        with self.assertRaises(frappe.PermissionError):
            ProductProposal.link_existing_item(
                proposal,
                "TEST-ITEM-001",
            )

        proposal.check_permission.assert_called_once_with("write")
        proposal.db_set.assert_not_called()

    def test_sync_preparation_bom_requires_write_permission(self):
        import frappe
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from taj_core.rnd.doctype.product_proposal.product_proposal import (
            ProductProposal,
        )

        proposal = Mock()
        proposal.check_permission.side_effect = frappe.PermissionError
        proposal.get.return_value = [
            SimpleNamespace(
                name="TEST-ROW-001",
                item_code="TEST-RAW-001",
                pre_bom=None,
            )
        ]

        with (
            patch(
                "taj_core.rnd.doctype.product_proposal."
                "product_proposal.frappe.get_all"
            ) as mock_get_all,
            patch(
                "taj_core.rnd.doctype.product_proposal."
                "product_proposal.frappe.db.set_value"
            ) as mock_set_value,
        ):
            mock_get_all.return_value = [
                ("TEST-RAW-001", "TEST-BOM-001")
            ]

            with self.assertRaises(frappe.PermissionError):
                ProductProposal.sync_preparation_bom(
                    proposal,
                )

        proposal.check_permission.assert_called_once_with("write")
        mock_set_value.assert_not_called()



class TestNewBulkCateringDelivery(TestCase):
    def test_new_bulk_delivery_does_not_read_itself_before_insert(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from taj_core.catering.doctype.catering_equipment_delivery import (
            catering_equipment_delivery as module,
        )

        equipment = SimpleNamespace(
            has_serial_no=0,
            total_qty=10,
            equipment_name_arabic="Test Equipment",
            check_permission=Mock(),
        )

        excluded_delivery = SimpleNamespace(
            check_permission=Mock(),
        )

        get_doc_calls = []

        def get_doc(doctype, name):
            get_doc_calls.append((doctype, name))

            if doctype == "Catering Equipment":
                return equipment

            if doctype == "Catering Equipment Delivery":
                return excluded_delivery

            raise AssertionError(
                f"Unexpected get_doc: {doctype} {name}"
            )

        delivery = SimpleNamespace(
            name="DEL-NEW",
            items=[
                SimpleNamespace(
                    equipment="EQ-TEST",
                    qty=1,
                )
            ],
            is_new=lambda: True,
        )

        with (
            patch.object(
                module.frappe,
                "get_doc",
                side_effect=get_doc,
            ),
            patch.object(
                module.frappe.db,
                "sql",
                return_value=[[0]],
            ),
        ):
            module.CateringEquipmentDelivery.validate_available_qty(
                delivery
            )

        self.assertNotIn(
            (
                "Catering Equipment Delivery",
                "DEL-NEW",
            ),
            get_doc_calls,
        )

        excluded_delivery.check_permission.assert_not_called()
