from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from taj_core.services.item_uom import (
    _get_same_category_global_factor,
)


class TestItemUOMGlobalCategory(FrappeTestCase):

    ROWS = [
        {
            "category": "Volume",
            "from_uom": "Litre",
            "to_uom": "Litre",
            "value": 1.0,
        },
        {
            "category": "Volume",
            "from_uom": "Litre",
            "to_uom": "Millilitre",
            "value": 1000.0,
        },
        {
            "category": "Mass",
            "from_uom": "Kg",
            "to_uom": "Kg",
            "value": 1.0,
        },
        {
            "category": "Mass",
            "from_uom": "Kg",
            "to_uom": "Gram",
            "value": 1000.0,
        },
        {
            "category": "Mass",
            "from_uom": "Gram",
            "to_uom": "Gram",
            "value": 1.0,
        },
        {
            "category": "Mass",
            "from_uom": "Bag (40k)",
            "to_uom": "Kg",
            "value": 40.0,
        },
        # Deliberately invalid cross-category row.
        {
            "category": "Mass",
            "from_uom": "Litre",
            "to_uom": "Gram",
            "value": 1000.0,
        },
    ]

    def _get_value(
        self,
        doctype,
        filters,
        fieldname=None,
        *args,
        **kwargs,
    ):
        if doctype != "UOM Conversion Factor":
            return None

        matches = [
            row
            for row in self.ROWS
            if all(
                row.get(key) == value
                for key, value in (filters or {}).items()
            )
        ]

        if not matches:
            return None

        row = matches[0]

        if isinstance(fieldname, (list, tuple)):
            return frappe._dict({
                field: row.get(field)
                for field in fieldname
            })

        return row.get(fieldname)

    def test_stock_to_smaller_uom_inverts_global_value(self):
        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=self._get_value,
        ):
            factor = _get_same_category_global_factor(
                "Millilitre",
                "Litre",
            )

        self.assertAlmostEqual(factor, 0.001)

    def test_mass_stock_to_smaller_uom_inverts_global_value(self):
        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=self._get_value,
        ):
            factor = _get_same_category_global_factor(
                "Gram",
                "Kg",
            )

        self.assertAlmostEqual(factor, 0.001)

    def test_candidate_to_stock_uses_global_value_directly(self):
        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=self._get_value,
        ):
            factor = _get_same_category_global_factor(
                "Bag (40k)",
                "Kg",
            )

        self.assertAlmostEqual(factor, 40.0)

    def test_wrong_category_is_rejected(self):
        with patch(
            "taj_core.services.item_uom.frappe.db.get_value",
            side_effect=self._get_value,
        ):
            factor = _get_same_category_global_factor(
                "Gram",
                "Litre",
            )

        self.assertIsNone(factor)
