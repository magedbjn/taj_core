import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate


class CateringMealPlan(Document):
    def validate(self):
        self.set_defaults()
        self.validate_required_fields()
        self.set_final_person_qty()
        self.validate_items()
        self.set_missing_child_values()

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------

    def set_defaults(self):
        if not self.plan_date:
            self.plan_date = nowdate()

        if not self.status:
            self.status = "Draft"

        if self.person_qty is None:
            self.person_qty = 0

        if self.actual_person_qty is None:
            self.actual_person_qty = 0

        if self.final_person_qty is None:
            self.final_person_qty = 0

    # -------------------------------------------------------------------------
    # Required Fields
    # -------------------------------------------------------------------------

    def validate_required_fields(self):
        if not self.plan_date:
            frappe.throw("Plan Date is required.")

        if not self.meal_type:
            frappe.throw("Meal Type is required.")

        if not self.menu_template:
            frappe.throw("Menu Template is required.")

        if flt(self.person_qty) <= 0 and flt(self.actual_person_qty) <= 0:
            frappe.throw("Person Qty or Actual Person Qty is required.")

    # -------------------------------------------------------------------------
    # Final Person Qty
    # -------------------------------------------------------------------------

    def set_final_person_qty(self):
        if flt(self.actual_person_qty) > 0:
            self.final_person_qty = flt(self.actual_person_qty)
        else:
            self.final_person_qty = flt(self.person_qty)

    # -------------------------------------------------------------------------
    # Items
    # -------------------------------------------------------------------------

    def validate_items(self):
        if not self.items:
            return

        seen_dishes = set()

        for row in self.items:
            if not row.dish:
                frappe.throw(f"Row #{row.idx}: Dish is required.")

            if row.dish in seen_dishes:
                frappe.throw(f"Row #{row.idx}: Dish '{row.dish}' is duplicated in this Meal Plan.")

            seen_dishes.add(row.dish)

    def set_missing_child_values(self):
        if not self.items:
            return

        for row in self.items:
            if row.person_qty is None or flt(row.person_qty) <= 0:
                row.person_qty = self.final_person_qty

            if row.is_required is None:
                row.is_required = 1

            if row.include_in_calculation is None:
                row.include_in_calculation = 1

            if row.print_in_menu is None:
                row.print_in_menu = 1

            self.fetch_dish_details(row)

    def fetch_dish_details(self, row):
        if not row.dish:
            return

        dish = frappe.db.get_value(
            "Catering Dish",
            row.dish,
            [
                "dish_name",
                "dish_name_arabic",
                "dish_type",
                "supply_mode",
                "default_section",
                "is_active",
                "show_in_menu_print",
            ],
            as_dict=True,
        )

        if not dish:
            frappe.throw(f"Row #{row.idx}: Catering Dish '{row.dish}' does not exist.")

        if not cint(dish.is_active):
            frappe.throw(f"Row #{row.idx}: Catering Dish '{row.dish}' is not active.")

        row.dish_name = dish.dish_name
        row.dish_name_arabic = dish.dish_name_arabic
        row.dish_type = dish.dish_type
        row.supply_mode = dish.supply_mode

        if not row.section:
            row.section = dish.default_section

        if row.print_in_menu is None:
            row.print_in_menu = cint(dish.show_in_menu_print or 1)

    # -------------------------------------------------------------------------
    # Generate From Template
    # -------------------------------------------------------------------------

    @frappe.whitelist()
    def generate_items_from_template(self):
        if not self.menu_template:
            frappe.throw("Menu Template is required.")

        if flt(self.final_person_qty) <= 0:
            self.set_final_person_qty()

        template = frappe.get_doc("Catering Menu Template", self.menu_template)

        if not cint(template.is_active):
            frappe.throw(f"Menu Template '{self.menu_template}' is not active.")

        if template.meal_type and self.meal_type and template.meal_type != self.meal_type:
            frappe.throw(
                f"Selected template meal type is '{template.meal_type}', "
                f"but Meal Plan meal type is '{self.meal_type}'."
            )

        self.items = []

        for template_row in template.items:
            if not template_row.dish:
                continue

            row = self.append("items", {})
            row.template_item = template_row.name
            row.dish = template_row.dish
            row.dish_name = template_row.dish_name
            row.dish_name_arabic = template_row.dish_name_arabic
            row.dish_type = template_row.dish_type
            row.supply_mode = template_row.supply_mode
            row.section = template_row.default_section
            row.person_qty = self.final_person_qty
            row.is_required = cint(template_row.is_required)
            row.include_in_calculation = cint(template_row.include_in_calculation)
            row.print_in_menu = cint(template_row.print_in_menu)
            row.notes = template_row.notes if hasattr(template_row, "notes") else None

            self.fetch_dish_details(row)

        self.status = "Generated"

        return {
            "items_count": len(self.items),
            "final_person_qty": self.final_person_qty,
            "status": self.status,
        }