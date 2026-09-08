import unittest
from pathlib import Path


class TestProductProposalTrialDialogSource(unittest.TestCase):
    def test_new_trial_dialog_avoids_frappe_prompt_double_get_values(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "rnd"
            / "doctype"
            / "product_proposal"
            / "product_proposal.js"
        )
        source = path.read_text()
        start = source.index("function create_new_trial(frm) {")
        end = source.index("function compare_product_trials(frm) {")
        block = source[start:end]

        self.assertIn("new frappe.ui.Dialog", block)
        self.assertIn("primary_action: async values =>", block)
        self.assertNotIn("frappe.prompt(", block)


if __name__ == "__main__":
    unittest.main()
