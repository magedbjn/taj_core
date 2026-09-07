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
            ProductProposalTrial.set_totals(
                fake
            )
        )

        with patch(
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial."
            "frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "valuation_rate": 5,
                    "last_purchase_rate": 8,
                })
            ],
        ):
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(
                    fake
                )
            )

        self.assertEqual(
            summary["costed"],
            1,
        )
        self.assertEqual(
            row.cost_source,
            "Valuation Rate",
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
            ProductProposalTrial.set_totals(
                fake
            )
        )

        with patch(
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial."
            "frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "valuation_rate": 0,
                    "last_purchase_rate": 7,
                })
            ],
        ):
            ProductProposalTrial.refresh_costs_from_items(
                fake
            )

        self.assertEqual(
            row.cost_source,
            "Last Purchase Rate",
        )
        self.assertEqual(
            row.amount,
            21,
        )

    def test_cost_ignores_uom_mismatch(self):
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
            ProductProposalTrial.set_totals(
                fake
            )
        )

        with patch(
            "taj_core.rnd.doctype."
            "product_proposal_trial."
            "product_proposal_trial."
            "frappe.get_all",
            return_value=[
                frappe._dict({
                    "name": "ITEM-A",
                    "stock_uom": "Kg",
                    "valuation_rate": 10,
                    "last_purchase_rate": 12,
                })
            ],
        ):
            summary = (
                ProductProposalTrial
                .refresh_costs_from_items(
                    fake
                )
            )

        self.assertEqual(
            summary["uom_mismatch"],
            1,
        )
        self.assertEqual(
            row.cost_status,
            "UOM Mismatch",
        )
        self.assertEqual(
            row.amount,
            0,
        )
        self.assertEqual(
            fake.total_cost,
            0,
        )


if __name__ == "__main__":
    unittest.main()
