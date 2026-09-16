import unittest
from unittest.mock import patch

import frappe

from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
)


class TestRNDTrialFormulaFlow(unittest.TestCase):
    def test_saved_run_does_not_lock_formula_before_formula_approval(self):
        old_doc = frappe._dict(
            formula_approved=0,
            cooking_runs=[frappe._dict(name="RUN-1")],
        )
        fake = frappe._dict(
            formula_approved=0,
            cooking_runs=[frappe._dict(name="RUN-1")],
        )
        fake.get_doc_before_save = lambda: old_doc

        ProductProposalTrial.validate_formula_locked_after_approval(fake)

    def test_formula_approval_locks_item_changes(self):
        old_doc = frappe._dict(formula_approved=1)
        fake = frappe._dict(formula_approved=1)
        fake.get_doc_before_save = lambda: old_doc
        fake._items_signature = (
            lambda doc=None: ("old",) if doc is old_doc else ("new",)
        )
        fake._solid_liquid_signature = lambda doc=None: ()

        with self.assertRaises(frappe.ValidationError):
            ProductProposalTrial.validate_formula_locked_after_approval(fake)

    def test_approve_formula_sets_explicit_lock_state(self):
        fake = frappe._dict(
            name="TRIAL-1",
            status="In Progress",
            formula_approved=0,
            items=[frappe._dict(item_code="RAW-1")],
        )
        fake.check_permission = lambda permission: None
        fake.save = lambda: fake.update(saved=True)

        result = ProductProposalTrial.approve_formula(fake)

        self.assertEqual(fake.formula_approved, 1)
        self.assertTrue(fake.saved)
        self.assertEqual(result["formula_approved"], 1)

    def test_replace_product_proposal_formula_replaces_all_rows(self):
        proposal = frappe._dict(
            name="PP-1",
            docstatus=0,
            pp_items=[frappe._dict(item_code="OLD-1")],
            pp_solid_liquid=[
                frappe._dict(component_name="OLD COMPONENT")
            ],
            flags=frappe._dict(),
        )
        proposal.check_permission = lambda permission: None
        proposal.set = lambda fieldname, value: setattr(
            proposal, fieldname, value
        )

        def append(fieldname, values):
            row = frappe._dict(values)
            getattr(proposal, fieldname).append(row)
            return row

        proposal.append = append
        proposal.save = lambda: proposal.update(saved=True)

        trial = frappe._dict(
            name="TRIAL-1",
            product_proposal="PP-1",
            status="Approved",
            is_final_trial=1,
            planned_cooking_qty=40,
            cooking_runs=[
                frappe._dict(run_no=1, produced_qty=38),
                frappe._dict(run_no=2, produced_qty=36.5),
            ],
            solid_liquid=[
                frappe._dict(
                    component_type="Liquid",
                    component_name="Final Sauce",
                    size="300 gm",
                    weight=300,
                    total_weight_cook=12000,
                    salt=1.2,
                    brix=8.5,
                    ph=4.2,
                    viscosity=1500,
                    spindel_type="3",
                    rpm=20,
                    temperature=85,
                )
            ],
            items=[
                frappe._dict(
                    item_code="RAW-1",
                    item_name="Raw One",
                    qty=2.5,
                    uom="Kg",
                    operation="Mixing",
                    procees_type="Weight",
                    cooking_type="",
                    temperature=0,
                    duration=0,
                    pre_bom=None,
                    notes="Final trial row",
                ),
                frappe._dict(
                    item_code="RAW-2",
                    item_name="Raw Two",
                    qty=750,
                    uom="Gram",
                    operation=None,
                    procees_type="Weight",
                    cooking_type="",
                    temperature=0,
                    duration=0,
                    pre_bom=None,
                    notes="",
                ),
            ],
        )
        trial.check_permission = lambda permission: None

        module = (
            "taj_core.rnd.doctype.product_proposal_trial."
            "product_proposal_trial"
        )
        with patch(f"{module}.frappe.get_doc", return_value=proposal):
            result = ProductProposalTrial.replace_product_proposal_formula(
                trial
            )

        self.assertTrue(proposal.saved)
        self.assertFalse(
            bool(proposal.flags.get("ignore_validate_update_after_submit"))
        )
        self.assertEqual(proposal.quantity, 36.5)
        self.assertEqual(
            [row.item_code for row in proposal.pp_items],
            ["RAW-1", "RAW-2"],
        )
        self.assertEqual(
            [row.qty for row in proposal.pp_items],
            [2.5, 750],
        )
        self.assertEqual(
            [row.uom for row in proposal.pp_items],
            ["Kg", "Gram"],
        )
        self.assertEqual(len(proposal.pp_solid_liquid), 1)
        self.assertEqual(
            proposal.pp_solid_liquid[0].component_name,
            "Final Sauce",
        )
        self.assertEqual(proposal.pp_solid_liquid[0].ph, 4.2)
        self.assertEqual(result["items_replaced"], 2)
        self.assertEqual(result["solid_liquid_replaced"], 1)
        self.assertEqual(result["quantity"], 36.5)
        self.assertEqual(result["run_no"], 2)


    def test_latest_run_requires_positive_produced_qty(self):
        proposal = frappe._dict(
            name="PP-1",
            docstatus=0,
            pp_items=[],
            pp_solid_liquid=[],
            flags=frappe._dict(),
        )
        proposal.check_permission = lambda permission: None

        trial = frappe._dict(
            name="TRIAL-1",
            product_proposal="PP-1",
            status="Approved",
            is_final_trial=1,
            cooking_runs=[
                frappe._dict(run_no=1, produced_qty=35),
                frappe._dict(run_no=2, produced_qty=0),
            ],
            items=[frappe._dict(item_code="RAW-1", qty=1, uom="Kg")],
            solid_liquid=[],
        )
        trial.check_permission = lambda permission: None

        module = (
            "taj_core.rnd.doctype.product_proposal_trial."
            "product_proposal_trial"
        )
        with patch(f"{module}.frappe.get_doc", return_value=proposal):
            with self.assertRaises(frappe.ValidationError):
                ProductProposalTrial.replace_product_proposal_formula(trial)

    def test_submitted_product_proposal_cannot_be_replaced(self):
        proposal = frappe._dict(
            name="PP-1",
            docstatus=1,
            pp_items=[frappe._dict(item_code="OLD-1")],
            flags=frappe._dict(),
        )
        proposal.check_permission = lambda permission: None
        proposal.set = lambda fieldname, value: setattr(
            proposal, fieldname, value
        )
        proposal.save = lambda: proposal.update(saved=True)

        trial = frappe._dict(
            name="TRIAL-1",
            product_proposal="PP-1",
            status="Approved",
            is_final_trial=1,
            items=[frappe._dict(item_code="RAW-1", qty=1, uom="Kg")],
        )
        trial.check_permission = lambda permission: None

        module = (
            "taj_core.rnd.doctype.product_proposal_trial."
            "product_proposal_trial"
        )
        with patch(f"{module}.frappe.get_doc", return_value=proposal):
            with self.assertRaises(frappe.ValidationError):
                ProductProposalTrial.replace_product_proposal_formula(trial)

        self.assertEqual([row.item_code for row in proposal.pp_items], ["OLD-1"])
        self.assertFalse(bool(proposal.get("saved")))

    def test_non_final_approved_trial_cannot_replace_product_proposal(self):
        trial = frappe._dict(
            name="TRIAL-1",
            product_proposal="PP-1",
            status="Approved",
            is_final_trial=0,
            items=[frappe._dict(item_code="RAW-1")],
        )
        trial.check_permission = lambda permission: None

        with self.assertRaises(frappe.ValidationError):
            ProductProposalTrial.replace_product_proposal_formula(trial)


if __name__ == "__main__":
    unittest.main()
