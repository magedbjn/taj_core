from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from taj_core.services.item_uom import get_item_uom_options


class TestItemUOMGlobalOptions(FrappeTestCase):

    def test_options_include_same_category_global_uoms(self):
        def get_value(doctype, name, fieldname=None, *args, **kwargs):
            if doctype == "Item":
                return frappe._dict({
                    "stock_uom": "Litre",
                    "variant_of": "",
                })

            if doctype == "UOM Conversion Factor":
                filters = name or {}

                if filters == {
                    "from_uom": "Litre",
                    "to_uom": "Litre",
                }:
                    return "Volume"

            return None

        def get_all(doctype, filters=None, fields=None, **kwargs):
            filters = filters or {}

            if doctype == "UOM Conversion Detail":
                return [
                    frappe._dict({
                        "uom": "P(17L)",
                        "conversion_factor": 17.0,
                    })
                ]

            if doctype == "UOM Conversion Factor":
                # List of UOMs belonging to Volume.
                if filters == {"category": "Volume"}:
                    return [
                        frappe._dict({
                            "category": "Volume",
                            "from_uom": "Litre",
                            "to_uom": "Litre",
                            "value": 1.0,
                        }),
                        frappe._dict({
                            "category": "Volume",
                            "from_uom": "Litre",
                            "to_uom": "Millilitre",
                            "value": 1000.0,
                        }),
                    ]

                # Direct candidate -> Stock UOM.
                if filters == {
                    "from_uom": "Millilitre",
                    "to_uom": "Litre",
                }:
                    return []

                # Reverse Stock UOM -> candidate.
                if filters == {
                    "from_uom": "Litre",
                    "to_uom": "Millilitre",
                }:
                    return [
                        frappe._dict({
                            "category": "Volume",
                            "value": 1000.0,
                        })
                    ]

            return []

        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=get_value,
        ), patch(
            "taj_core.services.item_uom.frappe.get_all",
            side_effect=get_all,
        ):
            result = get_item_uom_options("ITEM-A")

        options = {
            row["uom"]: row["conversion_factor"]
            for row in result["uoms"]
        }

        self.assertEqual(result["stock_uom"], "Litre")

        self.assertAlmostEqual(
            options["Litre"],
            1.0,
        )

        self.assertAlmostEqual(
            options["Millilitre"],
            0.001,
        )

        # Item-specific UOM must remain available.
        self.assertAlmostEqual(
            options["P(17L)"],
            17.0,
        )

        # Different category must not leak into the list.
        self.assertNotIn("Gram", options)
