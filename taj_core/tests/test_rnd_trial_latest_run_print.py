import unittest
from unittest.mock import patch

import frappe

from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
)


class TestRNDTrialLatestRunPrint(unittest.TestCase):
    def test_latest_run_helper_uses_highest_run_number(self):
        trial = frappe._dict(
            name="TRIAL-1",
            cooking_runs=[
                frappe._dict(run_no=1),
                frappe._dict(run_no=3),
                frappe._dict(run_no=2),
            ],
        )

        module = (
            "taj_core.rnd.doctype.product_proposal_trial."
            "product_proposal_trial"
        )
        with patch(
            f"{module}.get_trial_run_cooking_sheet",
            return_value=frappe._dict(run_no=3),
        ) as builder:
            result = ProductProposalTrial.get_latest_run_cooking_sheet(trial)

        builder.assert_called_once_with("TRIAL-1", 3)
        self.assertEqual(result.run_no, 3)

    def test_latest_run_helper_returns_none_without_runs(self):
        trial = frappe._dict(name="TRIAL-1", cooking_runs=[])

        result = ProductProposalTrial.get_latest_run_cooking_sheet(trial)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
