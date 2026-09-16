import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestRND20260913Regressions(unittest.TestCase):
    def test_existing_run_required_qty_is_compared_numerically(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        start = source.index("def validate_cooking_runs")
        end = source.index("def validate_formula_locked_after_approval", start)
        block = source[start:end]

        self.assertIn('fieldname == "required_qty"', block)
        self.assertIn("flt(row.get(fieldname))", block)
        self.assertIn("old_row.get(fieldname)", block)

    def test_product_proposal_items_use_raw_material_query(self):
        source = (
            ROOT / "rnd/doctype/product_proposal/product_proposal.js"
        ).read_text()
        self.assertIn(
            "set_raw_material_item_query(frm, 'pp_items')",
            source,
        )

    def test_trial_items_use_raw_material_query(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        self.assertIn(
            "set_raw_material_item_query(frm, 'items')",
            source,
        )

    def test_raw_material_query_includes_descendant_groups(self):
        source = (ROOT / "rnd/item_queries.py").read_text()
        self.assertIn('RAW_MATERIALS_ITEM_GROUP = "Raw Materials"', source)
        self.assertIn('"lft": [">=", bounds.lft]', source)
        self.assertIn('"rgt": ["<=", bounds.rgt]', source)
        self.assertIn('filters["item_group"] = ["in", groups]', source)

    def test_trial_status_includes_in_progress(self):
        meta = json.loads((
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.json"
        ).read_text())
        status = next(
            field for field in meta["fields"]
            if field.get("fieldname") == "status"
        )
        self.assertEqual(
            status["options"].split("\n"),
            ["Draft", "In Progress", "Completed", "Approved", "Rejected"],
        )

    def test_first_cooking_run_moves_draft_to_in_progress(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn("self.set_progress_status_from_cooking_runs()", source)
        self.assertIn('self.status == "Draft"', source)
        self.assertIn('self.status = "In Progress"', source)

    def test_in_progress_does_not_lock_formula_before_explicit_approval(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        self.assertIn(
            'if old_doc.status in ("Draft", "In Progress"):',
            source,
        )

        js = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
        ).read_text()
        self.assertIn("const frozen_statuses = ['Completed', 'Approved', 'Rejected'];", js)
        start = js.index("function is_trial_formula_locked(frm)")
        end = js.index("function show_trial_formula_lock_intro", start)
        lock_block = js[start:end]
        self.assertIn("frm.doc.formula_approved", lock_block)
        self.assertNotIn("frm.doc.status === 'In Progress'", lock_block)
        self.assertNotIn("cooking_runs", lock_block)

    def test_trial_title_is_set_after_trial_number_is_allocated(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        autoname_start = source.index("    def autoname(self):")
        before_insert_start = source.index("    def before_insert(self):", autoname_start)
        validate_start = source.index("    def validate(self):", before_insert_start)
        autoname_block = source[autoname_start:before_insert_start]
        before_insert_block = source[before_insert_start:validate_start]

        self.assertIn('self.trial_title = _(', autoname_block)
        self.assertIn('.format(self.trial_no)', autoname_block)
        self.assertNotIn('"Trial {0}"', before_insert_block)

    def test_holding_time_is_not_defaulted_to_current_clock_time(self):
        source = (
            ROOT
            / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
        ).read_text()
        before_insert_start = source.index("    def before_insert(self):")
        validate_start = source.index("    def validate(self):", before_insert_start)
        before_insert_block = source[before_insert_start:validate_start]
        self.assertNotIn("self.holding_time = nowtime()", before_insert_block)


if __name__ == "__main__":
    unittest.main()
