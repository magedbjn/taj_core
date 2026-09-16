import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative):
    return json.loads((ROOT / relative).read_text())


class TestProductProposalFinalRequirementsSource(unittest.TestCase):
    def test_legacy_trial_cooking_is_removed(self):
        proposal = load_json("rnd/doctype/product_proposal/product_proposal.json")
        fields = {row["fieldname"] for row in proposal["fields"]}
        self.assertNotIn("trial_cooking_tab", fields)
        self.assertNotIn("trial_cooking", fields)

        legacy = ROOT / "rnd/doctype/product_proposal_trial_cooking"
        self.assertFalse((legacy / "product_proposal_trial_cooking.json").exists())
        self.assertFalse((legacy / "product_proposal_trial_cooking.py").exists())

    def test_trial_has_solid_liquid_snapshot_and_cooking_runs(self):
        trial = load_json("rnd/doctype/product_proposal_trial/product_proposal_trial.json")
        fields = {row["fieldname"]: row for row in trial["fields"]}
        self.assertIn("solid_liquid", fields)
        self.assertIn("cooking_runs", fields)
        self.assertEqual(fields["solid_liquid"]["options"], "Product Proposal Trial Solid Liquid")
        self.assertEqual(fields["cooking_runs"]["options"], "Product Proposal Trial Run")

    def test_cooking_run_is_operational_only(self):
        path = ROOT / "rnd/doctype/product_proposal_trial_run/product_proposal_trial_run.json"
        self.assertTrue(path.exists(), "Product Proposal Trial Run must exist")
        data = json.loads(path.read_text())
        fields = {row["fieldname"]: row for row in data["fields"]}
        self.assertEqual(
            set(fields),
            {"run_no", "run_date", "required_qty", "produced_qty", "notes"},
        )
        self.assertEqual(fields["run_no"].get("read_only"), 1)
        self.assertEqual(fields["run_date"].get("reqd"), 1)
        self.assertEqual(fields["required_qty"].get("reqd"), 1)
        self.assertNotIn("purpose", fields)
        self.assertNotIn("yield_percent", fields)

    def test_trial_run_source_contains_no_yield_or_decision_analysis(self):
        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        js_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        template_path = ROOT / "rnd/templates/trial_run_cooking_sheet.html"
        self.assertTrue(template_path.exists(), "Trial Run Cooking Sheet must exist")
        template = template_path.read_text()
        for forbidden in ("yield_percent", "Yield %", "Pouch Achievement", "decision"):
            self.assertNotIn(forbidden, py_source)
            self.assertNotIn(forbidden, js_source)
            self.assertNotIn(forbidden, template)

    def test_product_proposal_trial_comparison_is_removed(self):
        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        js_source = (
            ROOT / "rnd/doctype/product_proposal/product_proposal.js"
        ).read_text()
        for forbidden in (
            "COMPARE_FIELDS",
            "def _compare_item_rows(",
            "def compare_trials(",
            "def _sensory_summary(",
            "Compare Trials",
            "compare_product_trials",
        ):
            self.assertNotIn(forbidden, py_source + "\n" + js_source)

    def test_cancelled_ai_analysis_modules_do_not_exist(self):
        forbidden_paths = (
            "rnd/doctype/rnd_ai_provider",
            "rnd/doctype/rnd_trial_analysis",
            "rnd/services/ai_providers.py",
            "rnd/services/trial_analysis.py",
            "rnd/services/trial_analysis_math.py",
        )
        for relative in forbidden_paths:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_new_trial_dialog_can_select_specific_based_on_trial(self):
        source = (
            ROOT / "rnd/doctype/product_proposal/product_proposal.js"
        ).read_text()
        start = source.index("function create_new_trial(frm) {")
        end = source.find("\nfunction ", start + 1)
        block = source[start:end if end != -1 else None]
        self.assertIn("fieldname: 'based_on_trial'", block)
        self.assertIn("options: 'Product Proposal Trial'", block)
        self.assertIn("product_proposal: frm.doc.name", block)
        self.assertIn("based_on_trial: values.based_on_trial", block)

    def test_trial_records_system_managed_approval_timestamp(self):
        trial = load_json("rnd/doctype/product_proposal_trial/product_proposal_trial.json")
        fields = {row["fieldname"]: row for row in trial["fields"]}
        self.assertIn("approved_on", fields)
        self.assertEqual(fields["approved_on"].get("fieldtype"), "Datetime")
        self.assertEqual(fields["approved_on"].get("read_only"), 1)

        source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn("def set_approval_timestamp(self):", source)
        self.assertIn("self.approved_on = now_datetime()", source)

    def test_approved_final_trial_replacement_preserves_history(self):
        source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn("def on_update(self):", source)
        self.assertIn("self._demote_other_final_trials()", source)
        self.assertIn("def _demote_other_final_trials(self):", source)
        self.assertIn("set is_final_trial = 0", source)
        self.assertIn("status = 'Approved'", source)
        self.assertIn("name != %s", source)
        self.assertIn("Approved Trial status cannot be changed", source)

    def test_solid_liquid_formula_locks_only_after_explicit_approval(self):
        py_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        js_source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        self.assertIn("SOLID_LIQUID_LOCKED_FIELDS", py_source)
        self.assertIn("def _solid_liquid_formula_signature", py_source)
        self.assertIn("SOLID_LIQUID_LOCKED_FIELDS", py_source)
        self.assertIn("function is_trial_formula_locked(frm)", js_source)
        self.assertIn(
            "frm.doc.formula_approved",
            js_source,
        )
        self.assertIn(
            "const formula_locked = is_trial_formula_locked(frm);",
            js_source,
        )
        self.assertIn("field.grid.cannot_add_rows = formula_locked", js_source)
        self.assertIn("field.grid.cannot_delete_rows = formula_locked", js_source)
        self.assertIn("formula_fields.forEach", js_source)
        self.assertIn("'total_weight_cook',\n        'read_only',\n        formula_locked ? 1 : 0", js_source)

    def test_trial_ui_orders_solid_liquid_before_items_and_sensory_dates_follow_toggle(self):
        trial = load_json("rnd/doctype/product_proposal_trial/product_proposal_trial.json")
        order = trial["field_order"]
        self.assertIn("solid_liquid", order)
        self.assertLess(order.index("solid_liquid"), order.index("items"))
        fields = {row["fieldname"]: row for row in trial["fields"]}
        self.assertIn("sensory_availability_section", fields)
        self.assertLess(order.index("sensory_availability_section"), order.index("enable_sensory_rating"))
        self.assertLess(order.index("enable_sensory_rating"), order.index("sensory_from_date"))
        self.assertEqual(fields["sensory_from_date"].get("depends_on"), "eval:doc.enable_sensory_rating")
        self.assertEqual(fields["sensory_until_date"].get("depends_on"), "eval:doc.enable_sensory_rating")

    def test_customer_sample_can_reference_trial_run(self):
        sample = load_json("rnd/doctype/product_proposal_sample/product_proposal_sample.json")
        fields = {row["fieldname"]: row for row in sample["fields"]}
        self.assertIn("trial_run_no", fields)
        self.assertEqual(fields["trial_run_no"]["fieldtype"], "Int")

    def test_trial_title_uses_trial_number(self):
        source = (
            ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn('"Trial {0}"', source)
        self.assertNotIn('"Trial None"', source)

    def test_chef_dashboard_is_standalone_page_linked_from_workspace(self):
        page = ROOT / "rnd/page/chef_dashboard/chef_dashboard.json"
        self.assertTrue(page.exists(), "Chef Dashboard Page must exist")
        data = json.loads(page.read_text())
        self.assertEqual(data.get("title"), "Chef Dashboard")

        workspace = load_json("rnd/workspace/r&d/r&d.json")
        links = workspace.get("links", [])
        dashboard = [row for row in links if row.get("label") == "Chef Dashboard"]
        self.assertEqual(len(dashboard), 1)
        self.assertEqual(dashboard[0].get("link_type"), "Page")
        self.assertEqual(dashboard[0].get("link_to"), "chef-dashboard")


if __name__ == "__main__":
    unittest.main()
