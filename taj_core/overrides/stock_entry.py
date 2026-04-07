import frappe
from frappe.utils import flt

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from taj_core.overrides.work_order import is_keep_rm_qty_enabled


class CustomStockEntry(StockEntry):
    def _matches_work_order_required_items(self) -> bool:
        if not (self.purpose == "Manufacture" and self.work_order and is_keep_rm_qty_enabled()):
            return False

        work_order = frappe.get_doc("Work Order", self.work_order)

        se_rm = {}
        for row in self.items:
            if row.s_warehouse and not row.is_finished_item and not row.is_scrap_item:
                key = (row.original_item or row.item_code, row.s_warehouse or "")
                se_rm[key] = flt(row.qty)

        wo_rm = {}
        for row in work_order.required_items:
            if not getattr(row, "include_item_in_manufacturing", 1):
                continue

            key = (getattr(row, "original_item", None) or row.item_code, row.source_warehouse or "")
            wo_rm[key] = flt(row.required_qty)

        return se_rm == wo_rm

    def validate_component_and_quantities(self):
        if self._matches_work_order_required_items():
            return

        super().validate_component_and_quantities()