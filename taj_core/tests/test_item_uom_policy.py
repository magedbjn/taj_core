import json
import frappe
import unittest
from pathlib import Path
from unittest.mock import patch

from taj_core.services import item_uom

from taj_core.rnd.doctype.product_proposal.product_proposal import ProductProposal
from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
)

from taj_core.services.item_uom import (
    get_item_uom_conversion_factor,
    get_item_uom_factor_to_stock,
)


ROOT = Path(__file__).resolve().parents[1]


class TestItemUOMPolicy(unittest.TestCase):
    def test_item_uom_does_not_fall_back_to_global_conversion(self):
        module = (
            "taj_core.services.item_uom"
        )

        with patch(
            f"{module}.frappe.db.get_value",
            return_value=None,
        ):
            factor = get_item_uom_factor_to_stock(
                item_code="LIQUID-ITEM",
                uom="Gram",
                stock_uom="Litre",
            )

        self.assertIsNone(
            factor,
            "A global UOM conversion must not authorize a UOM "
            "that is not configured on the Item.",
        )

    def test_rnd_item_tables_have_no_fixed_gram_default(self):
        paths = (
            ROOT
            / "rnd/doctype/product_proposal_raw_material/"
            "product_proposal_raw_material.json",
            ROOT
            / "rnd/doctype/product_proposal_trial_item/"
            "product_proposal_trial_item.json",
        )

        for path in paths:
            data = json.loads(path.read_text())
            fields = {
                row["fieldname"]: row
                for row in data["fields"]
                if row.get("fieldname")
            }

            with self.subTest(path=path.name):
                self.assertNotEqual(
                    fields["uom"].get("default"),
                    "Gram",
                    "R&D UOM must come from the selected Item, "
                    "not from a fixed Gram default.",
                )

    def test_item_specific_conversion_is_allowed(self):
        module = (
            "taj_core.services.item_uom"
        )

        def get_value(doctype, filters, fieldname, *args, **kwargs):
            if (
                doctype == "UOM Conversion Detail"
                and filters.get("parent") == "LIQUID-ITEM"
                and filters.get("uom") == "Millilitre"
                and fieldname == "conversion_factor"
            ):
                return 0.001

            return None

        with patch(
            f"{module}.frappe.db.get_value",
            side_effect=get_value,
        ):
            factor = get_item_uom_factor_to_stock(
                item_code="LIQUID-ITEM",
                uom="Millilitre",
                stock_uom="Litre",
            )

        self.assertEqual(factor, 0.001)


    def test_cross_uom_conversion_does_not_use_global_fallback(self):
        module = (
            "taj_core.services.item_uom"
        )

        with patch(
            f"{module}.frappe.db.get_value",
            return_value=None,
        ):
            factor = get_item_uom_conversion_factor(
                item_code="LIQUID-ITEM",
                from_uom="Gram",
                to_uom="Litre",
                stock_uom="Litre",
            )

        self.assertIsNone(
            factor,
            "Cross-UOM conversion must also require Item-specific "
            "UOM configuration.",
        )


    def test_item_uom_options_are_item_specific_and_stock_uom_first(self):
        def get_value(doctype, name, fieldname, *args, **kwargs):
            if doctype == "Item" and name == "LIQUID-ITEM":
                if fieldname == ["stock_uom", "variant_of"]:
                    return {
                        "stock_uom": "Litre",
                        "variant_of": None,
                    }

            return None

        def get_all(doctype, *args, **kwargs):
            if doctype != "UOM Conversion Detail":
                return []

            filters = kwargs.get("filters") or {}
            if filters.get("parent") != "LIQUID-ITEM":
                return []

            return [
                {
                    "uom": "Millilitre",
                    "conversion_factor": 0.001,
                },
                {
                    "uom": "Litre",
                    "conversion_factor": 1.0,
                },
            ]

        get_options = getattr(
            item_uom,
            "get_item_uom_options",
            None,
        )

        self.assertTrue(
            callable(get_options),
            "Shared Taj Core UOM service must expose "
            "get_item_uom_options().",
        )

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            with patch(
                "taj_core.services.item_uom.frappe.get_all",
                side_effect=get_all,
            ):
                result = get_options("LIQUID-ITEM")

        self.assertEqual(result["stock_uom"], "Litre")
        self.assertEqual(
            result["uoms"],
            [
                {
                    "uom": "Litre",
                    "conversion_factor": 1.0,
                },
                {
                    "uom": "Millilitre",
                    "conversion_factor": 0.001,
                },
            ],
        )


    def test_validate_item_uom_rejects_unconfigured_uom(self):
        validator = getattr(
            item_uom,
            "validate_item_uom",
            None,
        )

        self.assertTrue(
            callable(validator),
            "Shared Taj Core UOM service must expose validate_item_uom().",
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Item" and name_or_filters == "LIQUID-ITEM":
                return frappe._dict(
                    stock_uom="Litre",
                    variant_of=None,
                )

            if doctype == "UOM Conversion Detail":
                return None

            return None

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            with self.assertRaises(frappe.ValidationError):
                validator(
                    "LIQUID-ITEM",
                    "Gram",
                )

    def test_validate_item_uom_accepts_stock_uom(self):
        validator = getattr(
            item_uom,
            "validate_item_uom",
            None,
        )

        self.assertTrue(callable(validator))

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            return_value=frappe._dict(
                stock_uom="Litre",
                variant_of=None,
            ),
        ):
            factor = validator(
                "LIQUID-ITEM",
                "Litre",
            )

        self.assertEqual(factor, 1.0)

    def test_validate_item_uom_accepts_item_conversion(self):
        validator = getattr(
            item_uom,
            "validate_item_uom",
            None,
        )

        self.assertTrue(callable(validator))

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Item" and name_or_filters == "LIQUID-ITEM":
                return frappe._dict(
                    stock_uom="Litre",
                    variant_of=None,
                )

            if (
                doctype == "UOM Conversion Detail"
                and isinstance(name_or_filters, dict)
                and name_or_filters.get("parent") == "LIQUID-ITEM"
                and name_or_filters.get("uom") == "Millilitre"
            ):
                return 0.001

            return None

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            factor = validator(
                "LIQUID-ITEM",
                "Millilitre",
            )

        self.assertEqual(factor, 0.001)


    def test_shared_row_validator_rejects_invalid_item_uom(self):
        validator = getattr(
            item_uom,
            "validate_item_uom_rows",
            None,
        )

        self.assertTrue(
            callable(validator),
            "Shared service must expose validate_item_uom_rows().",
        )

        rows = [
            frappe._dict(
                item_code="LIQUID-ITEM",
                uom="Gram",
            )
        ]

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Item" and name_or_filters == "LIQUID-ITEM":
                return frappe._dict(
                    stock_uom="Litre",
                    variant_of=None,
                )

            if doctype == "UOM Conversion Detail":
                return None

            return None

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            with self.assertRaises(frappe.ValidationError):
                validator(rows)

    def test_product_proposal_uses_shared_item_uom_validation(self):
        validator = getattr(
            ProductProposal,
            "validate_item_uoms",
            None,
        )

        self.assertTrue(
            callable(validator),
            "Product Proposal must validate Raw Material UOMs.",
        )

        doc = frappe._dict(
            pp_items=[
                frappe._dict(
                    item_code="LIQUID-ITEM",
                    uom="Gram",
                )
            ]
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Item" and name_or_filters == "LIQUID-ITEM":
                return frappe._dict(
                    stock_uom="Litre",
                    variant_of=None,
                )

            if doctype == "UOM Conversion Detail":
                return None

            return None

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            with self.assertRaises(frappe.ValidationError):
                validator(doc)

    def test_product_proposal_trial_uses_shared_item_uom_validation(self):
        validator = getattr(
            ProductProposalTrial,
            "validate_item_uoms",
            None,
        )

        self.assertTrue(
            callable(validator),
            "Product Proposal Trial must validate Item UOMs.",
        )

        doc = frappe._dict(
            items=[
                frappe._dict(
                    item_code="LIQUID-ITEM",
                    uom="Gram",
                )
            ]
        )

        def get_value(doctype, name_or_filters, fieldname, *args, **kwargs):
            if doctype == "Item" and name_or_filters == "LIQUID-ITEM":
                return frappe._dict(
                    stock_uom="Litre",
                    variant_of=None,
                )

            if doctype == "UOM Conversion Detail":
                return None

            return None

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ):
            with self.assertRaises(frappe.ValidationError):
                validator(doc)


if __name__ == "__main__":
    unittest.main()
