import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
    _compare_item_rows,
)


def make_row(
    line_key,
    item_code,
    qty,
    **kwargs,
):
    return frappe._dict({
        "line_key": line_key,
        "item_code": item_code,
        "item_name": kwargs.get(
            "item_name",
            item_code,
        ),
        "qty": qty,
        "uom": kwargs.get("uom", "Kg"),
        "operation": kwargs.get("operation"),
        "procees_type": kwargs.get(
            "procees_type"
        ),
        "cooking_type": kwargs.get(
            "cooking_type"
        ),
        "temperature": kwargs.get(
            "temperature"
        ),
        "duration": kwargs.get(
            "duration"
        ),
        "pre_bom": kwargs.get("pre_bom"),
        "notes": kwargs.get("notes"),
    })


class TestTrialCooking(unittest.TestCase):
    def test_comparison_detects_added_removed_changed(self):
        first = SimpleNamespace(
            items=[
                make_row("A", "ITEM-A", 10),
                make_row("B", "ITEM-B", 20),
                make_row("C", "ITEM-C", 30),
            ]
        )

        second = SimpleNamespace(
            items=[
                make_row("A", "ITEM-A", 10),
                make_row("B", "ITEM-B", 25),
                make_row("D", "ITEM-D", 40),
            ]
        )

        changes, unchanged = _compare_item_rows(
            first,
            second,
        )

        by_key = {
            row["line_key"]: row
            for row in changes
        }

        self.assertEqual(unchanged, 1)

        self.assertEqual(
            by_key["B"]["change_type"],
            "Changed",
        )
        self.assertEqual(
            by_key["B"]["old_qty"],
            20,
        )
        self.assertEqual(
            by_key["B"]["new_qty"],
            25,
        )

        self.assertEqual(
            by_key["C"]["change_type"],
            "Removed",
        )
        self.assertEqual(
            by_key["D"]["change_type"],
            "Added",
        )

    def test_comparison_detects_process_change(self):
        first = SimpleNamespace(
            items=[
                make_row(
                    "A",
                    "ITEM-A",
                    10,
                    cooking_type="Boiled",
                ),
            ]
        )

        second = SimpleNamespace(
            items=[
                make_row(
                    "A",
                    "ITEM-A",
                    10,
                    cooking_type="Steam",
                ),
            ]
        )

        changes, unchanged = _compare_item_rows(
            first,
            second,
        )

        self.assertEqual(unchanged, 0)
        self.assertEqual(len(changes), 1)

        fields = {
            change["fieldname"]
            for change in changes[0]["changes"]
        }

        self.assertIn(
            "cooking_type",
            fields,
        )

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

if __name__ == "__main__":
    unittest.main()
