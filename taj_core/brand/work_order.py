"""Native Work Order BOM preview with Brand-aware raw material rows (v16)."""

import frappe

from .bom import bom_brand_map
from .rules import brand
from .validation import require_tracked_brand


class BrandAwareWorkOrder:
    """Keep the ERPNext controller; add the BOM Brand to its unsaved preview."""

    @frappe.whitelist(methods=["POST"])
    def get_items_and_operations_from_bom(self):
        result = super().get_items_and_operations_from_bom()
        if not self.get("bom_no"):
            return result

        requirements = bom_brand_map(
            self.bom_no, bool(self.get("use_multi_level_bom"))
        )
        for row in self.get("required_items") or []:
            if not row.get("item_code"):
                continue
            expected = brand(requirements.get(row.item_code))
            require_tracked_brand(row.item_code, expected, "Work Order")
            row.taj_required_brand = expected
        return result
