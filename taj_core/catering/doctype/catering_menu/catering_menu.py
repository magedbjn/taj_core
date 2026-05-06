import frappe
from frappe.model.document import Document


class CateringMenu(Document):
    def validate(self):
        self.set_new_item_row_ids()
        self.normalize_rows()
        self.validate_menu_rows()
        self.validate_sub_item_links()
        self.set_parent_row_labels()

    def make_row_id(self):
        return "ROW-" + frappe.generate_hash(length=10).upper()

    def set_new_item_row_ids(self):
        used_row_ids = set()

        for row in self.get("items") or []:
            if row.row_type == "New Item":
                if not row.row_id:
                    row.row_id = self.make_row_id()

                if row.row_id in used_row_ids:
                    frappe.throw(
                        f"Row #{row.idx}: Duplicate Row ID {row.row_id}."
                    )

                used_row_ids.add(row.row_id)

    def normalize_rows(self):
        for row in self.get("items") or []:
            if row.row_type == "Section":
                row.item_code = None
                row.item_name = None
                row.item_name_arabic = None
                row.new_item_name = None
                row.new_item_name_arabic = None
                row.qty = 0
                row.uom = None
                row.parent_row_id = None
                row.parent_row_label = None

            elif row.row_type == "New Item":
                row.section = None
                row.item_code = None
                row.item_name = None
                row.item_name_arabic = None
                row.qty = 0
                row.uom = None
                row.parent_row_id = None
                row.parent_row_label = None

            elif row.row_type == "Item":
                row.section = None
                row.new_item_name = None
                row.new_item_name_arabic = None
                row.parent_row_id = None
                row.parent_row_label = None

            elif row.row_type == "Sub Item":
                row.section = None
                row.new_item_name = None
                row.new_item_name_arabic = None
                row.row_id = None

    def validate_menu_rows(self):
        for row in self.get("items") or []:
            if not row.service_period:
                frappe.throw(
                    f"Row #{row.idx}: Service Period is required."
                )

            if not row.meal_type:
                frappe.throw(
                    f"Row #{row.idx}: Meal Type is required."
                )

            if not row.row_type:
                frappe.throw(
                    f"Row #{row.idx}: Row Type is required."
                )

            if row.row_type == "Section":
                if not row.section:
                    frappe.throw(
                        f"Row #{row.idx}: Section is required."
                    )

            elif row.row_type == "New Item":
                if not row.row_id:
                    frappe.throw(
                        f"Row #{row.idx}: Row ID is required for New Item."
                    )

                if not row.new_item_name and not row.new_item_name_arabic:
                    frappe.throw(
                        f"Row #{row.idx}: New Item Name or New Item Name Arabic is required."
                    )

            elif row.row_type in ["Item", "Sub Item"]:
                if not row.item_code:
                    frappe.throw(
                        f"Row #{row.idx}: Item Code is required for {row.row_type}."
                    )

                if not row.qty:
                    frappe.throw(
                        f"Row #{row.idx}: QTY is required for {row.row_type}."
                    )

                if not row.uom:
                    frappe.throw(
                        f"Row #{row.idx}: UOM is required for {row.row_type}."
                    )

                if row.row_type == "Sub Item" and not row.parent_row_id:
                    frappe.throw(
                        f"Row #{row.idx}: Sub Item must be linked to a New Item using Parent Row ID."
                    )

    def get_new_item_map(self):
        new_item_map = {}

        for row in self.get("items") or []:
            if row.row_type == "New Item" and row.row_id:
                new_item_map[row.row_id] = row

        return new_item_map

    def validate_sub_item_links(self):
        new_item_map = self.get_new_item_map()

        for row in self.get("items") or []:
            if row.row_type != "Sub Item":
                continue

            parent = new_item_map.get(row.parent_row_id)

            if not parent:
                frappe.throw(
                    f"Row #{row.idx}: Parent Row ID {row.parent_row_id} is not linked to a valid New Item."
                )

            if row.service_period != parent.service_period:
                frappe.throw(
                    f"Row #{row.idx}: Sub Item Service Period must match the linked New Item."
                )

            if row.meal_type != parent.meal_type:
                frappe.throw(
                    f"Row #{row.idx}: Sub Item Meal Type must match the linked New Item."
                )

    def set_parent_row_labels(self):
        new_item_map = self.get_new_item_map()

        for row in self.get("items") or []:
            if row.row_type != "Sub Item":
                continue

            parent = new_item_map.get(row.parent_row_id)

            if parent:
                row.parent_row_label = (
                    parent.new_item_name_arabic
                    or parent.new_item_name
                    or parent.row_id
                )