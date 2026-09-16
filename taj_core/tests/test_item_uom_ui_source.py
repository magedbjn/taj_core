import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HELPER = ROOT / "public/js/item_uom.js"
PROPOSAL_JS = (
    ROOT
    / "rnd/doctype/product_proposal/product_proposal.js"
)
HOOKS = ROOT / "hooks.py"

TRIAL_JS = (
    ROOT
    / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
)


class TestItemUOMUISource(unittest.TestCase):
    def test_shared_item_uom_helper_exists(self):
        self.assertTrue(
            HELPER.exists(),
            "Taj Core must provide one reusable Item UOM UI helper.",
        )

    def test_shared_helper_uses_taj_core_uom_service(self):
        self.assertTrue(HELPER.exists())
        source = HELPER.read_text()

        self.assertIn(
            "taj_core.services.item_uom.get_item_uom_options",
            source,
        )
        self.assertIn(
            "taj_core.services.item_uom.item_uom_query",
            source,
        )

    def test_product_proposal_uses_shared_uom_helper(self):
        source = PROPOSAL_JS.read_text()

        self.assertIn(
            "taj_core.item_uom.setup_grid",
            source,
        )
        self.assertIn(
            "taj_core.item_uom.apply_item_default",
            source,
        )

    def test_product_proposal_trial_uses_shared_uom_helper(self):
        source = TRIAL_JS.read_text()

        self.assertIn(
            "taj_core.item_uom.setup_grid",
            source,
        )
        self.assertIn(
            "taj_core.item_uom.apply_item_default",
            source,
        )


    def test_shared_helper_is_loaded_in_desk(self):
        source = HOOKS.read_text()

        self.assertIn(
            "/assets/taj_core/js/item_uom.js",
            source,
        )


    def test_uom_helper_calls_do_not_break_form_when_asset_is_unavailable(self):
        proposal = PROPOSAL_JS.read_text()
        trial = TRIAL_JS.read_text()

        for source in (proposal, trial):
            self.assertIn(
                "frappe.require(",
                source,
            )
            self.assertIn(
                "/assets/taj_core/js/item_uom.js",
                source,
            )
            self.assertIn(
                "window.taj_core",
                source,
            )



if __name__ == "__main__":
    unittest.main()
