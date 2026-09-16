import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative):
    return json.loads((ROOT / relative).read_text())


class TestRNDTrialCookingRunsSource(unittest.TestCase):
    def test_legacy_trial_cooking_is_removed_from_product_proposal(self):
        data = load_json("rnd/doctype/product_proposal/product_proposal.json")
        fieldnames = {row["fieldname"] for row in data["fields"]}
        self.assertNotIn("trial_cooking_tab", fieldnames)
        self.assertNotIn("trial_cooking", fieldnames)
        legacy_dir = ROOT / "rnd/doctype/product_proposal_trial_cooking"
        self.assertFalse((legacy_dir / "product_proposal_trial_cooking.json").exists())
        self.assertFalse((legacy_dir / "product_proposal_trial_cooking.py").exists())

        py_source = (
            ROOT / "rnd/doctype/product_proposal/product_proposal.py"
        ).read_text()
        js_source = (
            ROOT / "rnd/doctype/product_proposal/product_proposal.js"
        ).read_text()
        self.assertNotIn("set_trial_cooking_defaults", py_source)
        self.assertNotIn("validate_trial_cooking_permission", py_source)
        self.assertNotIn("TRIAL_COOKING_TABLE", js_source)
        self.assertNotIn("new_pp.trial_cooking", js_source)

    def test_trial_contains_solid_liquid_snapshot_and_cooking_runs(self):
        data = load_json(
            "rnd/doctype/product_proposal_trial/product_proposal_trial.json"
        )
        fields = {row["fieldname"]: row for row in data["fields"]}
        self.assertEqual(
            fields["solid_liquid"]["options"],
            "Product Proposal Trial Solid Liquid",
        )
        self.assertEqual(
            fields["cooking_runs"]["options"],
            "Product Proposal Trial Run",
        )

    def test_trial_solid_liquid_formula_is_editable_before_formula_approval(self):
        data = load_json(
            "rnd/doctype/product_proposal_trial_solid_liquid/"
            "product_proposal_trial_solid_liquid.json"
        )
        fields = {row["fieldname"]: row for row in data["fields"]}
        for fieldname in (
            "component_type",
            "component_name",
            "size",
            "weight",
            "salt",
            "brix",
            "ph",
            "viscosity",
            "spindel_type",
            "rpm",
            "temperature",
            "total_weight_cook",
        ):
            self.assertNotEqual(fields[fieldname].get("read_only"), 1)

        js_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        self.assertIn("field.grid.cannot_add_rows = formula_locked", js_source)
        self.assertIn("field.grid.cannot_delete_rows = formula_locked", js_source)
        self.assertIn("formula_fields.forEach", js_source)
        self.assertIn("formula_locked ? 1 : 0", js_source)
        self.assertIn("frozen ? 1 : 0", js_source)

        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn(
            'if not cint(old_doc.get("formula_approved")):',
            py_source,
        )

    def test_cooking_run_has_only_agreed_operational_fields(self):
        data = load_json(
            "rnd/doctype/product_proposal_trial_run/"
            "product_proposal_trial_run.json"
        )
        fields = {row["fieldname"]: row for row in data["fields"]}
        self.assertEqual(
            set(fields),
            {"run_no", "run_date", "required_qty", "produced_qty", "notes"},
        )
        self.assertEqual(fields["required_qty"].get("reqd"), 1)
        self.assertEqual(fields["run_no"].get("read_only"), 1)
        self.assertNotIn("purpose", fields)
        self.assertNotIn("yield_percent", fields)

    def test_cooking_sheet_source_exists(self):
        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        js_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        template = ROOT / "rnd/templates/trial_run_cooking_sheet.html"

        self.assertIn("def get_trial_run_cooking_sheet(", py_source)
        self.assertIn("def get_trial_run_cooking_sheet_html(", py_source)
        self.assertIn("Print Cooking Sheet", js_source)
        self.assertTrue(template.exists())
        html = template.read_text()
        self.assertIn("Materials", html)
        self.assertIn("Solid / Liquid", html)
        self.assertNotIn("Purpose", html)
        self.assertNotIn("Yield", html)

    def test_customer_sample_can_reference_trial_run_number(self):
        data = load_json(
            "rnd/doctype/product_proposal_sample/product_proposal_sample.json"
        )
        fields = {row["fieldname"]: row for row in data["fields"]}
        self.assertEqual(fields["trial_run_no"]["fieldtype"], "Int")

    def test_sensory_date_does_not_use_literal_today(self):
        data = load_json("rnd/web_form/sensory_rating/sensory_rating.json")
        fields = {row["fieldname"]: row for row in data["web_form_fields"]}
        self.assertNotIn("evaluation_date", fields)

        feedback_source = (
            ROOT / "rnd/doctype/sensory_feedback/sensory_feedback.py"
        ).read_text()
        self.assertIn(
            "def set_evaluation_date_default",
            feedback_source,
        )
        self.assertIn(
            "self.evaluation_date = today()",
            feedback_source,
        )

    def test_solid_liquid_snapshot_comparison_normalizes_numeric_values(self):
        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn("from taj_core.rnd.services.snapshot_compare import", py_source)
        self.assertIn("snapshot_values_equal(", py_source)
        self.assertIn("normalize_snapshot_value(", py_source)

    def test_legacy_delete_patch_is_registered(self):
        patches = (ROOT / "patches.txt").read_text()
        self.assertIn(
            "taj_core.patches.2026_09_09_remove_legacy_product_proposal_trial_cooking",
            patches,
        )
        self.assertTrue(
            (
                ROOT
                / "patches/2026_09_09_remove_legacy_product_proposal_trial_cooking.py"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
