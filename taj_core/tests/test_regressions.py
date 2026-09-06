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
