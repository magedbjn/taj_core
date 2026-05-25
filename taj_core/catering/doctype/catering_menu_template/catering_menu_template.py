import frappe
from frappe.model.document import Document
from frappe.utils import cint


class CateringMenuTemplate(Document):
    def validate(self):
        self.set_defaults()
        self.validate_required_fields()
        self.validate_items()
        self.set_missing_child_values()

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------

    def set_defaults(self):
        if self.is_active is None:
            self.is_active = 1

    # -------------------------------------------------------------------------
    # Required Fields
    # -------------------------------------------------------------------------

    def validate_required_fields(self):
        if not self.template_name:
            frappe.throw("Template Name is required.")

        if not self.meal_type:
            frappe.throw("Meal Type is required.")

    # -------------------------------------------------------------------------
    # Items Validation
    # -------------------------------------------------------------------------

    def validate_items(self):
        if not self.items:
            frappe.throw("At least one dish is required in the menu template.")

        seen_dishes = set()

        for row in self.items:
            if not row.dish:
                frappe.throw(f"Row #{row.idx}: Dish is required.")

            if row.dish in seen_dishes:
                frappe.throw(f"Row #{row.idx}: Dish '{row.dish}' is duplicated in this template.")

            seen_dishes.add(row.dish)

    # -------------------------------------------------------------------------
    # Child Defaults
    # -------------------------------------------------------------------------

    def set_missing_child_values(self):
        for row in self.items:
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

        if not row.default_section:
            row.default_section = dish.default_section

        if row.print_in_menu is None:
            row.print_in_menu = cint(dish.show_in_menu_print or 1)