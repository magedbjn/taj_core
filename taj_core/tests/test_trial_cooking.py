import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
    _get_item_uom_conversion_factor,
    _scale_snapshot_qty,
    _scale_total_weight_cook,
)



class TestTrialCooking(unittest.TestCase):
    def test_scale_snapshot_qty(self):
        self.assertAlmostEqual(
            _scale_snapshot_qty(100, 10, 50),
            5,
        )

    def test_scale_total_weight_cook(self):
        self.assertAlmostEqual(
            _scale_total_weight_cook(23, 46, 100),
            200,
        )

    def test_scale_snapshot_qty_rejects_zero_source(self):
        with self.assertRaises(frappe.ValidationError):
            _scale_snapshot_qty(0, 10, 50)

    def test_scale_snapshot_qty_rejects_zero_target(self):
        with self.assertRaises(frappe.ValidationError):
            _scale_snapshot_qty(100, 0, 50)

    def test_planned_cooking_qty_is_locked_after_insert(self):
        old_doc = frappe._dict({
            "product_proposal": "PP-TEST",
            "trial_no": 1,
            "based_on_trial": None,
            "posting_date": "2026-09-08",
            "trial_user": "Administrator",
            "planned_cooking_qty": 10,
        })

        fake = frappe._dict({
            "product_proposal": "PP-TEST",
            "trial_no": 1,
            "based_on_trial": None,
            "posting_date": "2026-09-08",
            "trial_user": "Administrator",
            "planned_cooking_qty": 20,
        })
        fake.get_doc_before_save = lambda: old_doc

        with self.assertRaises(frappe.ValidationError):
            ProductProposalTrial.validate_locked_identity(fake)

    def test_duplicate_line_keys_are_repaired(self):
        rows = [
            frappe._dict(
                line_key="SAME"
            ),
            frappe._dict(
                line_key="SAME"
            ),
        ]

        fake = SimpleNamespace(
            items=rows
        )

        ProductProposalTrial.ensure_line_keys(
            fake
        )

        self.assertNotEqual(
            rows[0].line_key,
            rows[1].line_key,
        )

    def test_final_trial_requires_approved_status(self):
        fake = SimpleNamespace(
            is_final_trial=1,
            status="Completed",
        )

        with self.assertRaises(
            frappe.ValidationError
        ):
            ProductProposalTrial.validate_final_trial(
                fake
            )

    def test_completed_trial_cannot_return_to_draft(self):
        old_doc = frappe._dict(
            status="Completed"
        )

        class FakeTrial:
            status = "Draft"

            @staticmethod
            def get_doc_before_save():
                return old_doc

        with self.assertRaises(
            frappe.ValidationError
        ):
            ProductProposalTrial.validate_frozen_snapshot(
                FakeTrial()
            )


    def test_approval_timestamp_is_set_when_status_becomes_approved(self):
        old_doc = frappe._dict(status="Completed", approved_on=None)
        fake = frappe._dict(status="Approved", approved_on=None)
        fake.get_doc_before_save = lambda: old_doc

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )
        approved_at = "2026-09-11 15:30:00"
        with patch(f"{module}.now_datetime", return_value=approved_at):
            ProductProposalTrial.set_approval_timestamp(fake)

        self.assertEqual(fake.approved_on, approved_at)

    def test_existing_approved_timestamp_cannot_be_rewritten(self):
        old_doc = frappe._dict(
            status="Approved",
            approved_on="2026-09-10 09:00:00",
        )
        fake = frappe._dict(
            status="Approved",
            approved_on="2099-01-01 00:00:00",
        )
        fake.get_doc_before_save = lambda: old_doc

        ProductProposalTrial.set_approval_timestamp(fake)

        self.assertEqual(fake.approved_on, "2026-09-10 09:00:00")

    def test_final_trial_allows_draft_product_proposal(self):
        fake = SimpleNamespace(
            name="TRIAL-1",
            is_final_trial=1,
            status="Approved",
            product_proposal="PP-TEST",
        )

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            f"{module}.frappe.db.sql",
            return_value=[],
        ):
            ProductProposalTrial.validate_final_trial(fake)

    def test_item_uom_conversion_uses_stock_uom_ratio(self):
        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            "taj_core.services.item_uom.get_item_uom_factor_to_stock",
            side_effect=[0.001, 1],
        ):
            factor = _get_item_uom_conversion_factor(
                "ITEM-A",
                "Gram",
                "Kg",
                "Kg",
            )

        self.assertAlmostEqual(factor, 0.001)

    def test_item_uom_conversion_does_not_invent_missing_factor(self):
        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            "taj_core.services.item_uom.get_item_uom_factor_to_stock",
            return_value=None,
        ):
            factor = _get_item_uom_conversion_factor(
                "ITEM-A",
                "Gram",
                "Litre",
                "Kg",
            )

        self.assertIsNone(factor)


    def test_cost_uses_valuation_rate_when_uom_matches(self):
        row = frappe._dict({
            "item_code": "ITEM-A",
            "qty": 2,
            "uom": "Kg",
            "stock_uom": None,
            "conversion_factor": 0,
            "stock_qty": 0,
            "unit_cost": 0,
            "amount": 0,
            "cost_source": "",
            "cost_status": "",
        })

        fake = SimpleNamespace(
            items=[row],
            total_items=0,
            total_cost=0,
        )

        fake.set_totals = lambda: (
            ProductProposalTrial.set_totals(fake)
        )

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            f"{module}.frappe.db.get_single_value",
            return_value="Taj Foods",
        ), patch(
            f"{module}.frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "last_purchase_rate": 8,
                    "variant_of": "",
                })
            ],
        ), patch(
            f"{module}._get_trial_conversion_factor",
            return_value=1,
        ), patch(
            f"{module}.get_valuation_rate",
            return_value=5,
        ):
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(fake)
            )

        self.assertEqual(summary["costed"], 1)
        self.assertEqual(
            summary["missing_conversion"],
            0,
        )
        self.assertEqual(
            row.cost_source,
            "Valuation Rate",
        )
        self.assertEqual(
            row.cost_status,
            "OK",
        )
        self.assertEqual(
            row.stock_uom,
            "Kg",
        )
        self.assertEqual(
            row.conversion_factor,
            1,
        )
        self.assertEqual(
            row.stock_qty,
            2,
        )
        self.assertEqual(
            row.unit_cost,
            5,
        )
        self.assertEqual(
            row.amount,
            10,
        )
        self.assertEqual(
            fake.total_cost,
            10,
        )

    def test_cost_falls_back_to_last_purchase_rate(self):
        row = frappe._dict({
            "item_code": "ITEM-A",
            "qty": 3,
            "uom": "Kg",
            "stock_uom": None,
            "conversion_factor": 0,
            "stock_qty": 0,
            "unit_cost": 0,
            "amount": 0,
            "cost_source": "",
            "cost_status": "",
        })

        fake = SimpleNamespace(
            items=[row],
            total_items=0,
            total_cost=0,
        )

        fake.set_totals = lambda: (
            ProductProposalTrial.set_totals(fake)
        )

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            f"{module}.frappe.db.get_single_value",
            return_value="Taj Foods",
        ), patch(
            f"{module}.frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "last_purchase_rate": 7,
                    "variant_of": "",
                })
            ],
        ), patch(
            f"{module}._get_trial_conversion_factor",
            return_value=1,
        ), patch(
            f"{module}.get_valuation_rate",
            return_value=0,
        ):
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(fake)
            )

        self.assertEqual(summary["costed"], 1)
        self.assertEqual(
            row.cost_source,
            "Last Purchase Rate",
        )
        self.assertEqual(
            row.cost_status,
            "OK",
        )
        self.assertEqual(
            row.unit_cost,
            7,
        )
        self.assertEqual(
            row.amount,
            21,
        )
        self.assertEqual(
            fake.total_cost,
            21,
        )

    def test_cost_uses_uom_conversion(self):
        row = frappe._dict({
            "item_code": "ITEM-A",
            "qty": 500,
            "uom": "Gram",
            "stock_uom": None,
            "conversion_factor": 0,
            "stock_qty": 0,
            "unit_cost": 0,
            "amount": 0,
            "cost_source": "",
            "cost_status": "",
        })

        fake = SimpleNamespace(
            items=[row],
            total_items=0,
            total_cost=0,
        )

        fake.set_totals = lambda: (
            ProductProposalTrial.set_totals(fake)
        )

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            f"{module}.frappe.db.get_single_value",
            return_value="Taj Foods",
        ), patch(
            f"{module}.frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "last_purchase_rate": 12,
                    "variant_of": "",
                })
            ],
        ), patch(
            f"{module}._get_trial_conversion_factor",
            return_value=0.001,
        ), patch(
            f"{module}.get_valuation_rate",
            return_value=10,
        ):
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(fake)
            )

        self.assertEqual(summary["costed"], 1)
        self.assertEqual(
            row.cost_status,
            "OK",
        )
        self.assertAlmostEqual(
            row.conversion_factor,
            0.001,
        )
        self.assertAlmostEqual(
            row.stock_qty,
            0.5,
        )
        self.assertAlmostEqual(
            row.unit_cost,
            0.01,
        )
        self.assertAlmostEqual(
            row.amount,
            5,
        )
        self.assertAlmostEqual(
            fake.total_cost,
            5,
        )

    def test_cost_marks_missing_conversion(self):
        row = frappe._dict({
            "item_code": "ITEM-A",
            "qty": 500,
            "uom": "Gram",
            "stock_uom": None,
            "conversion_factor": 0,
            "stock_qty": 0,
            "unit_cost": 0,
            "amount": 0,
            "cost_source": "",
            "cost_status": "",
        })

        fake = SimpleNamespace(
            items=[row],
            total_items=0,
            total_cost=0,
        )

        fake.set_totals = lambda: (
            ProductProposalTrial.set_totals(fake)
        )

        module = (
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(
            f"{module}.frappe.db.get_single_value",
            return_value="Taj Foods",
        ), patch(
            f"{module}.frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Litre",
                    "last_purchase_rate": 12,
                    "variant_of": "",
                })
            ],
        ), patch(
            f"{module}._get_trial_conversion_factor",
            return_value=None,
        ), patch(
            f"{module}.get_valuation_rate",
        ) as valuation_mock:
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(fake)
            )

        self.assertEqual(summary["costed"], 0)
        self.assertEqual(
            summary["missing_conversion"],
            1,
        )
        self.assertEqual(
            row.cost_status,
            "Missing Conversion",
        )
        self.assertEqual(
            row.conversion_factor,
            0,
        )
        self.assertEqual(
            row.stock_qty,
            0,
        )
        self.assertEqual(
            row.unit_cost,
            0,
        )
        self.assertEqual(
            row.amount,
            0,
        )
        self.assertEqual(
            fake.total_cost,
            0,
        )

        valuation_mock.assert_not_called()


class TestSensoryTrialLink(unittest.TestCase):
    def test_trial_link_sets_server_managed_product_proposal(self):
        from taj_core.rnd.doctype.sensory_feedback.sensory_feedback import (
            SensoryFeedback,
        )

        fake = SimpleNamespace(
            trial_document="PP-OTHER-TRIAL-01",
            item="PP-TEST",
        )

        module = (
            "taj_core.rnd.doctype."
            "sensory_feedback.sensory_feedback"
        )

        with patch(
            f"{module}.frappe.db.get_value",
            return_value="PP-OTHER",
        ):
            SensoryFeedback.validate_trial_document(
                fake
            )

        self.assertEqual(
            fake.item,
            "PP-OTHER",
        )


if __name__ == "__main__":
    unittest.main()
