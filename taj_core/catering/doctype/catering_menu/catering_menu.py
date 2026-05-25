import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class CateringMenu(Document):
    def validate(self):
        self.validate_dish_lines()

    def validate_dish_lines(self):
        for row in self.get("dish_lines") or []:
            if not row.service_period:
                frappe.throw(_("Dish Line #{0}: Service Period is required.").format(row.idx))

            if not row.meal_type:
                frappe.throw(_("Dish Line #{0}: Meal Type is required.").format(row.idx))

            has_dish = bool(row.dish)
            has_package = bool(row.meal_package)

            if has_dish and has_package:
                frappe.throw(
                    _("Dish Line #{0}: Select either Dish or Meal Package, not both.").format(row.idx)
                )

            if not has_dish and not has_package:
                frappe.throw(
                    _("Dish Line #{0}: Dish or Meal Package is required.").format(row.idx)
                )

    def generate_items(self):
        self.validate_dish_lines()
        self.set("items", [])

        added_sections = set()

        lines = sorted(
            self.get("dish_lines") or [],
            key=lambda d: ((d.sort_order or 0), (d.idx or 0))
        )

        for line in lines:
            if line.dish:
                self._append_dish_from_line(line, added_sections)

            elif line.meal_package:
                self._append_package_from_line(line, added_sections)

        self.generated_items_updated = 1
        self.last_generated_on = now()
        self.last_generated_by = frappe.session.user
        self.has_validation_errors = 0

    def _append_package_from_line(self, line, added_sections):
        package = frappe.get_doc("Catering Meal Package", line.meal_package)

        if not package.is_active:
            frappe.throw(_("Meal Package {0} is not active.").format(package.name))

        for package_item in package.get("items") or []:
            if not package_item.dish:
                frappe.throw(
                    _("Meal Package {0}, Row #{1}: Dish is required.").format(
                        package.name, package_item.idx
                    )
                )

            virtual_line = frappe._dict({
                "service_period": line.service_period,
                "meal_type": line.meal_type,
                "section": package_item.section,
                "dish": package_item.dish,
                "qty_per_person": package_item.qty_per_person,
                "uom": package_item.uom,
                "show_in_menu_print": package_item.show_in_menu_print,
                "include_in_purchase": package_item.include_in_purchase,
                "include_in_production": package_item.include_in_production,
                "sort_order": package_item.sort_order or line.sort_order,
                "source_dish_line": f"{line.name}:{package_item.name}",
                "notes": package_item.notes or line.notes,
            })

            self._append_dish_from_line(virtual_line, added_sections)

    def _append_dish_from_line(self, line, added_sections):
        dish = frappe.get_doc("Catering Dish", line.dish)

        if not dish.is_active:
            frappe.throw(_("Dish {0} is not active.").format(dish.name))

        dish_type = self._get_dish_type(dish.dish_type)

        section = line.section or dish.default_section
        if not section:
            frappe.throw(_("Dish {0}: Default Section is required.").format(dish.name))

        self._ensure_section_row(
            service_period=line.service_period,
            meal_type=line.meal_type,
            section=section,
            added_sections=added_sections,
        )

        row_type = (
            dish.generate_as_row_type
            or (dish_type.default_row_type if dish_type else None)
        )

        if not row_type:
            frappe.throw(_("Dish {0}: Generate As Row Type or Dish Type Default Row Type is required.").format(dish.name))

        if row_type == "Item":
            self._append_item_row(line, dish, section)

        elif row_type == "New Item":
            self._append_new_item_row(line, dish, section)
            self._append_material_rows(line, dish, section, dish_type)

        else:
            frappe.throw(_("Dish {0}: Unsupported row type {1}.").format(dish.name, row_type))

    def _ensure_section_row(self, service_period, meal_type, section, added_sections):
        key = (service_period, meal_type, section)

        if key in added_sections:
            return

        self.append("items", {
            "service_period": service_period,
            "meal_type": meal_type,
            "row_type": "Section",
            "section": section,
            "is_show_print": 1,
            "menu_group": section,
            "qty": 0,
        })

        added_sections.add(key)

    def _append_item_row(self, line, dish, section):
        if not dish.item_code:
            frappe.throw(_("Dish {0}: Item Code is required.").format(dish.name))

        item_details = self._get_item_details(dish.item_code)

        self.append("items", {
            "service_period": line.service_period,
            "meal_type": line.meal_type,
            "row_type": "Item",
            "item_code": dish.item_code,
            "item_name": item_details.get("item_name"),
            "item_name_arabic": item_details.get("item_name_arabic"),
            "qty": line.qty_per_person or dish.default_qty_per_person or 1,
            "uom": line.uom or dish.default_uom or item_details.get("stock_uom"),
            "is_show_print": self._as_int(line.show_in_menu_print, dish.show_in_menu_print),
            "menu_group": section,
            "buffet_location": None,
            "source_dish": dish.name,
            "source_dish_line": getattr(line, "source_dish_line", None) or line.name,
            "workstation": dish.default_workstation,
            "operation": dish.main_operation,
            "temperature": dish.default_temperature,
            "cooking_time": self._minutes_to_time(dish.default_duration_minutes),
            "note": getattr(line, "notes", None),
        })

    def _append_new_item_row(self, line, dish, section):
        self.append("items", {
            "service_period": line.service_period,
            "meal_type": line.meal_type,
            "row_type": "New Item",
            "new_item_name": dish.dish_name,
            "new_item_name_arabic": dish.dish_name_arabic,
            "qty": 0,
            "uom": None,
            "is_show_print": self._as_int(line.show_in_menu_print, dish.show_in_menu_print),
            "menu_group": section,
            "source_dish": dish.name,
            "source_dish_line": getattr(line, "source_dish_line", None) or line.name,
            "workstation": dish.default_workstation,
            "operation": dish.main_operation,
            "temperature": dish.default_temperature,
            "cooking_time": self._minutes_to_time(dish.default_duration_minutes),
            "note": dish.cooking_instructions or getattr(line, "notes", None),
        })

    def _append_material_rows(self, line, dish, section, dish_type):
        materials = dish.get("materials") or []

        if dish_type and dish_type.requires_recipe and not materials:
            frappe.throw(_("Dish {0}: Materials are required.").format(dish.name))

        for material in materials:
            if not material.material_item:
                frappe.throw(_("Dish {0}, Material Row #{1}: Material Item is required.").format(dish.name, material.idx))

            if not material.qty_per_person:
                frappe.throw(_("Dish {0}, Material Row #{1}: Qty Per Person is required.").format(dish.name, material.idx))

            if not material.uom:
                frappe.throw(_("Dish {0}, Material Row #{1}: UOM is required.").format(dish.name, material.idx))

            item_details = self._get_item_details(material.material_item)

            self.append("items", {
                "service_period": line.service_period,
                "meal_type": line.meal_type,
                "row_type": "Sub Item",
                "item_code": material.material_item,
                "item_name": item_details.get("item_name"),
                "item_name_arabic": item_details.get("item_name_arabic"),
                "qty": material.qty_per_person,
                "uom": material.uom,
                "is_show_print": 0,
                "menu_group": section,
                "source_dish": dish.name,
                "source_dish_line": getattr(line, "source_dish_line", None) or line.name,
                "workstation": material.workstation or dish.default_workstation,
                "operation": material.operation or dish.main_operation,
                "temperature": dish.default_temperature,
                "cooking_time": self._minutes_to_time(dish.default_duration_minutes),
                "note": material.notes,
            })

        if not materials and dish.item_code:
            item_details = self._get_item_details(dish.item_code)

            self.append("items", {
                "service_period": line.service_period,
                "meal_type": line.meal_type,
                "row_type": "Sub Item",
                "item_code": dish.item_code,
                "item_name": item_details.get("item_name"),
                "item_name_arabic": item_details.get("item_name_arabic"),
                "qty": line.qty_per_person or dish.default_qty_per_person or 1,
                "uom": line.uom or dish.default_uom or item_details.get("stock_uom"),
                "is_show_print": 0,
                "menu_group": section,
                "source_dish": dish.name,
                "source_dish_line": getattr(line, "source_dish_line", None) or line.name,
                "workstation": dish.default_workstation,
                "operation": dish.main_operation,
                "temperature": dish.default_temperature,
                "cooking_time": self._minutes_to_time(dish.default_duration_minutes),
                "note": dish.cooking_instructions,
            })

    def _get_dish_type(self, dish_type):
        if not dish_type:
            return None

        if not frappe.db.exists("Catering Dish Type", dish_type):
            return None

        return frappe.get_doc("Catering Dish Type", dish_type)

    def _get_item_details(self, item_code):
        if not item_code:
            return {}

        meta = frappe.get_meta("Item")
        fields = ["item_name", "stock_uom"]

        if meta.has_field("item_name_arabic"):
            fields.append("item_name_arabic")

        values = frappe.db.get_value("Item", item_code, fields, as_dict=True) or {}

        return {
            "item_name": values.get("item_name"),
            "item_name_arabic": values.get("item_name_arabic"),
            "stock_uom": values.get("stock_uom"),
        }

    def _minutes_to_time(self, minutes):
        if not minutes:
            return None

        minutes = int(minutes)
        hours = minutes // 60
        mins = minutes % 60

        return f"{hours:02d}:{mins:02d}:00"

    def _as_int(self, value, fallback=0):
        if value is None:
            value = fallback

        return 1 if value else 0


@frappe.whitelist()
def generate_items(catering_menu):
    doc = frappe.get_doc("Catering Menu", catering_menu)
    doc.generate_items()
    doc.save(ignore_permissions=False)

    return {
        "generated_items_updated": doc.generated_items_updated,
        "last_generated_on": doc.last_generated_on,
        "last_generated_by": doc.last_generated_by,
        "items_count": len(doc.get("items") or []),
    }

@frappe.whitelist()
def generate_items_button(self):
    self.generate_items()
    self.save()

    return {
        "items_count": len(self.get("items") or []),
        "last_generated_on": self.last_generated_on,
        "last_generated_by": self.last_generated_by,
    }