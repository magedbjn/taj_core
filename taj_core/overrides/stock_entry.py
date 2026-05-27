# Copyright (c) 2026, Taj
# Custom Stock Entry override for ERPNext

import frappe
from frappe.utils import cint, flt

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from taj_core.overrides.work_order import is_keep_rm_qty_enabled


# -------------------------------------------------------------------------
# Customization Note
# Date: 2026-05-25
#
# Class: CustomStockEntry
#
# This override keeps the standard ERPNext StockEntry behavior unchanged.
#
# The only customized behavior is inside validate_component_and_quantities.
#
# Standard ERPNext behavior:
# - ERPNext validates raw material quantities against the BOM when
#   validate_components_quantities_per_bom is enabled.
#
# Custom behavior:
# - If the Stock Entry purpose is "Manufacture",
# - and the Stock Entry is linked to a Work Order,
# - and the custom Manufacturing Settings field "taj_keep_rm_qty" is enabled,
# - and the raw material quantities in the Stock Entry match the Work Order
#   required_items quantities,
# then the BOM component quantity validation is skipped.
#
# Purpose:
# Allow Manufacture Stock Entry raw material quantities to follow the
# Work Order required_items quantities instead of being rejected by the
# standard BOM quantity validation.
#
# No other standard ERPNext StockEntry behavior is intentionally changed.
# -------------------------------------------------------------------------


class CustomStockEntry(StockEntry):
	def _get_raw_material_qty_map_from_stock_entry(self) -> dict:
		"""
		Return raw material quantities from the current Stock Entry.

		Key format:
		(original_item_or_item_code, source_warehouse)

		Finished goods and scrap rows are ignored.
		Duplicate rows for the same item and warehouse are summed.
		"""
		precision = frappe.get_precision("Stock Entry Detail", "qty")
		rm_qty_map = {}

		for row in self.get("items"):
			if row.get("is_finished_item"):
				continue

			if row.get("is_scrap_item"):
				continue

			if not row.get("s_warehouse"):
				continue

			item_code = row.get("original_item") or row.get("item_code")
			source_warehouse = row.get("s_warehouse") or ""
			key = (item_code, source_warehouse)

			rm_qty_map[key] = flt(rm_qty_map.get(key, 0) + flt(row.get("qty")), precision)

		return rm_qty_map

	def _get_raw_material_qty_map_from_work_order(self) -> dict:
		"""
		Return raw material quantities from Work Order required_items.

		Key format:
		(original_item_or_item_code, source_warehouse)

		Rows excluded from manufacturing are ignored.
		Duplicate rows for the same item and warehouse are summed.
		"""
		precision = frappe.get_precision("Stock Entry Detail", "qty")
		rm_qty_map = {}

		work_order = frappe.get_doc("Work Order", self.work_order)

		for row in work_order.get("required_items"):
			if not cint(getattr(row, "include_item_in_manufacturing", 1)):
				continue

			item_code = getattr(row, "original_item", None) or row.item_code
			source_warehouse = row.source_warehouse or ""
			key = (item_code, source_warehouse)

			rm_qty_map[key] = flt(rm_qty_map.get(key, 0) + flt(row.required_qty), precision)

		return rm_qty_map

	def _matches_work_order_required_items(self) -> bool:
		"""
		Return True only when this Manufacture Stock Entry raw material
		quantities exactly match the linked Work Order required_items.
		"""
		if self.purpose != "Manufacture":
			return False

		if not self.work_order:
			return False

		if not is_keep_rm_qty_enabled():
			return False

		stock_entry_rm_qty = self._get_raw_material_qty_map_from_stock_entry()
		work_order_rm_qty = self._get_raw_material_qty_map_from_work_order()

		return stock_entry_rm_qty == work_order_rm_qty

	def validate_component_and_quantities(self):
		"""
		Skip standard BOM component quantity validation only when the
		Manufacture Stock Entry already matches Work Order required_items.

		Otherwise, run the standard ERPNext validation.
		"""
		if self._matches_work_order_required_items():
			return

		super().validate_component_and_quantities()