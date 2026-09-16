import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIAL_JSON = ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.json"
TRIAL_PY = ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
TRIAL_JS = ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
PROPOSAL_JSON = ROOT / "rnd/doctype/product_proposal/product_proposal.json"


class TestRNDTrialFormulaFlowSource(unittest.TestCase):
    def test_trial_has_explicit_formula_approved_state(self):
        data = json.loads(TRIAL_JSON.read_text())
        fields = {row["fieldname"]: row for row in data["fields"]}

        self.assertIn("formula_approved", fields)
        self.assertEqual(fields["formula_approved"]["fieldtype"], "Check")
        self.assertEqual(fields["formula_approved"].get("read_only"), 1)

    def test_run_does_not_lock_formula_before_explicit_approval(self):
        py_source = TRIAL_PY.read_text()
        js_source = TRIAL_JS.read_text()

        self.assertIn("def validate_formula_locked_after_approval", py_source)
        self.assertNotIn("def validate_formula_locked_after_runs", py_source)
        self.assertIn("old_doc.get(\"formula_approved\")", py_source)

        start = js_source.index("function is_trial_formula_locked(frm)")
        end = js_source.index("function show_trial_formula_lock_intro", start)
        block = js_source[start:end]
        self.assertIn("frm.doc.formula_approved", block)
        self.assertNotIn("frm.doc.status === 'In Progress'", block)
        self.assertNotIn("cooking_runs", block)

    def test_formula_approval_action_is_exposed_in_trial_ui(self):
        js_source = TRIAL_JS.read_text()
        py_source = TRIAL_PY.read_text()

        self.assertIn("Approve Formula Quantities", js_source)
        self.assertIn("approve_trial_formula(frm)", js_source)
        self.assertIn("def approve_formula(self):", py_source)

    def test_approved_final_trial_can_replace_product_proposal_formula(self):
        js_source = TRIAL_JS.read_text()
        py_source = TRIAL_PY.read_text()

        self.assertIn("Update Product Proposal Formula", js_source)
        self.assertIn("replace_product_proposal_formula(frm)", js_source)
        self.assertIn("def replace_product_proposal_formula(self):", py_source)
        self.assertIn('self.status != "Approved"', py_source)
        self.assertIn("not cint(self.is_final_trial)", py_source)
        self.assertIn('proposal.set("pp_items", [])', py_source)
        self.assertIn("proposal.append(", py_source)
        self.assertIn('"pp_items",', py_source)
        self.assertNotIn("proposal.flags.ignore_validate_update_after_submit = True", py_source)
        self.assertIn("Product Proposal must be in Draft", py_source)
        self.assertIn("proposal.save()", py_source)

    def test_formula_transfer_updates_product_proposal_base_quantity(self):
        py_source = TRIAL_PY.read_text()
        start = py_source.index(
            "    def replace_product_proposal_formula(self):"
        )
        end = py_source.index(
            "    def get_latest_run_cooking_sheet(self):",
            start,
        )
        block = py_source[start:end]

        self.assertIn(
            "proposal.quantity = flt(latest_run.produced_qty)",
            block,
        )
        self.assertIn('proposal.set("pp_solid_liquid", [])', block)
        self.assertIn('"pp_solid_liquid",', block)
        self.assertIn("SOLID_LIQUID_SNAPSHOT_FIELDS", block)
        self.assertIn("latest_run.produced_qty", block)
        self.assertNotIn(
            "proposal.quantity = flt(self.planned_cooking_qty)",
            block,
        )

    def test_product_proposal_quantity_supports_fractional_produced_qty(self):
        data = json.loads(PROPOSAL_JSON.read_text())
        fields = {row["fieldname"]: row for row in data["fields"]}

        self.assertEqual(fields["quantity"]["fieldtype"], "Float")

    def test_final_trial_does_not_require_submitted_product_proposal(self):
        py_source = TRIAL_PY.read_text()
        start = py_source.index("    def validate_final_trial(self):")
        end = py_source.index("    def on_update(self):", start)
        block = py_source[start:end]

        self.assertNotIn("must be submitted", block)
        self.assertIn("from `tabProduct Proposal`", block)
        self.assertGreaterEqual(block.lower().count("for update"), 2)


if __name__ == "__main__":
    unittest.main()
