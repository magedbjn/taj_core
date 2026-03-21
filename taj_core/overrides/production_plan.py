import frappe
from frappe import _
from frappe.utils import flt

from erpnext.manufacturing.doctype.production_plan.production_plan import (
    ProductionPlan as ERPNextProductionPlan,
    get_sub_assembly_items as build_sub_assembly_items,
)


class CustomProductionPlan(ERPNextProductionPlan):
    SPLIT_FIELD = "taj_sub_assembly_items_split"

    def _make_merge_key(self, row):
        return "||".join(
            [
                str(row.get("production_item") or row.get("sub_assembly_item_code") or ""),
                str(row.get("fg_warehouse") or ""),
                str(row.get("bom_no") or row.get("sub_assembly_bom_no") or ""),
                str(row.get("type_of_manufacturing") or ""),
            ]
        )

    def _make_temp_source_name(self):
        return f"TMP-SA-{frappe.generate_hash(length=10)}"

    def _append_split_row(self, source_po_row, source_temp_name, sub_row):
        self.append(
            self.SPLIT_FIELD,
            {
                "source_assembly_item": source_po_row.name,
                "source_fg_item_code": source_po_row.item_code,
                "source_fg_bom_no": source_po_row.bom_no,
                "assembly_qty": flt(source_po_row.planned_qty),
                "source_sub_assembly_item": source_temp_name,
                "source_sub_assembly_item_copy": source_temp_name,
                "sub_assembly_item_code": sub_row.get("production_item"),
                "sub_assembly_bom_no": sub_row.get("bom_no"),
                "sub_assembly_qty": flt(sub_row.get("qty") or sub_row.get("stock_qty")),
                "merged_key": self._make_merge_key(sub_row),
                "merged_sub_assembly_item": "",
                "merge_group_id": "",
            },
        )

    def _link_split_rows_to_final_rows(self, source_name_to_final_name):
        split_rows = self.get(self.SPLIT_FIELD) or []
        if not split_rows:
            return

        if self.combine_sub_items:
            key_to_final = {}

            for row in self.get("sub_assembly_items") or []:
                key_to_final[self._make_merge_key(row)] = row.name

            for split in split_rows:
                final_name = key_to_final.get(split.merged_key, "")
                split.merged_sub_assembly_item = final_name
                split.merge_group_id = final_name
        else:
            for split in split_rows:
                final_name = source_name_to_final_name.get(split.source_sub_assembly_item, "")
                split.source_sub_assembly_item = final_name
                split.merge_group_id = final_name

    @frappe.whitelist()
    def get_sub_assembly_items(self, manufacturing_type=None):
        self.set("sub_assembly_items", [])
        self.set(self.SPLIT_FIELD, [])

        sub_assembly_items_store = []
        source_name_to_final_name = {}
        bin_details = frappe._dict()

        for row in self.po_items:
            if self.skip_available_sub_assembly_item and not self.sub_assembly_warehouse:
                frappe.throw(_("Row #{0}: Please select the Sub Assembly Warehouse").format(row.idx))

            if not row.item_code:
                frappe.throw(_("Row #{0}: Please select Item Code in Assembly Items").format(row.idx))

            if not row.bom_no:
                frappe.throw(_("Row #{0}: Please select the BOM No in Assembly Items").format(row.idx))

            bom_data = []

            build_sub_assembly_items(
                [item.production_item for item in sub_assembly_items_store],
                bin_details,
                row.bom_no,
                bom_data,
                row.planned_qty,
                self.company,
                warehouse=self.sub_assembly_warehouse,
                skip_available_sub_assembly_item=self.skip_available_sub_assembly_item,
            )

            self.set_sub_assembly_items_based_on_level(row, bom_data, manufacturing_type)

            for sub_row in bom_data:
                temp_name = self._make_temp_source_name()
                sub_row["name"] = temp_name
                self._append_split_row(row, temp_name, sub_row)

            sub_assembly_items_store.extend(bom_data)

        if not sub_assembly_items_store and self.skip_available_sub_assembly_item:
            message = (
                _(
                    "As there are sufficient Sub Assembly Items, Work Order is not required for Warehouse {0}."
                ).format(self.sub_assembly_warehouse)
                + "<br><br>"
            )
            message += _(
                "If you still want to proceed, please disable 'Skip Available Sub Assembly Items' checkbox."
            )
            frappe.msgprint(message, title=_("Note"))

        if self.combine_sub_items:
            sub_assembly_items_store = self.combine_subassembly_items(sub_assembly_items_store)

        for idx, sub_row in enumerate(sub_assembly_items_store, start=1):
            original_temp_name = sub_row.get("name")
            sub_row.idx = idx
            appended = self.append("sub_assembly_items", sub_row)

            if original_temp_name:
                source_name_to_final_name[original_temp_name] = appended.name

        self._link_split_rows_to_final_rows(source_name_to_final_name)
        self.set_default_supplier_for_subcontracting_order()