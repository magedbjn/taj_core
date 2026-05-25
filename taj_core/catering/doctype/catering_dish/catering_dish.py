import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class CateringDish(Document):
    def validate(self):
        self.set_default_values()
        self.set_status_flags()
        self.validate_required_fields()
        self.validate_output_planning()
        self.validate_materials()
        self.validate_run_setup()

    def set_default_values(self):
        self.is_active = 1 if self.is_active is None else self.is_active
        self.output_planning_method = self.output_planning_method or "Manual"
        self.output_rounding_method = self.output_rounding_method or "Round Up"
        self.receiving_display_method = self.receiving_display_method or "Required Qty"
        self.test_person_qty = self.test_person_qty or 100
        self.show_output_coverage_difference = 1 if self.show_output_coverage_difference is None else self.show_output_coverage_difference
        self.show_output_qty_difference = 0 if self.show_output_qty_difference is None else self.show_output_qty_difference

    def set_status_flags(self):
        self.has_materials = 1 if self.materials else 0
        self.has_operation_settings = 1 if (
            self.default_workstation or self.workstation_calculation_method
            or flt(self.workstation_load_qty) > 0 or self.workstation_load_uom
            or flt(self.default_temperature) > 0 or flt(self.default_duration_minutes) > 0
            or flt(self.holding_temperature) > 0 or flt(self.holding_duration_minutes) > 0
        ) else 0

    def validate_required_fields(self):
        if not self.dish_name:
            frappe.throw("Dish Name is required.")
        if not self.dish_type:
            frappe.throw("Dish Type is required.")
        if not self.default_section:
            frappe.throw("Default Section is required.")
        if self.dish_type != "Display Only" and not self.supply_mode:
            frappe.throw("Supply Mode is required.")
        if cint(self.requires_item_code) and not self.item_code:
            frappe.throw(f"Item Code is required for Dish Type: {self.dish_type}")
        if cint(self.requires_recipe) and not self.materials:
            frappe.throw(f"Materials are required for Dish Type: {self.dish_type}")

    def validate_output_planning(self):
        method = self.output_planning_method or "Manual"
        allowed = ["Dish Qty Per Person", "Covers Persons", "Output Driver Material", "Sum Output Materials", "Per Buffet", "Manual"]
        if method not in allowed:
            frappe.throw(f"Invalid Output Planning Method: {method}")
        if method == "Manual":
            return
        if not self.output_container_uom:
            frappe.throw(f"Output Container UOM is required for Output Planning Method: {method}")
        if method == "Dish Qty Per Person":
            if flt(self.recipe_basis_qty) <= 0 or not self.default_uom:
                frappe.throw("Default Recipe Basis Qty and UOM are required for Dish Qty Per Person.")
            if flt(self.output_container_capacity_qty) <= 0 or not self.output_container_capacity_uom:
                frappe.throw("Output Container Capacity Qty and UOM are required for Dish Qty Per Person.")
        elif method == "Covers Persons":
            if flt(self.recipe_basis_qty) <= 0:
                frappe.throw("Default Recipe Basis Qty is required for Covers Persons.")
            if self.default_uom != "Person":
                frappe.throw("Default Recipe Basis UOM must be Person for Covers Persons.")
        elif method == "Output Driver Material":
            drivers = [row for row in (self.materials or []) if (row.material__calculation_base or "Per Person") == "Output Driver"]
            if not drivers:
                frappe.throw("One material must be marked as Output Driver.")
            if len(drivers) > 1:
                frappe.throw("Only one material can be marked as Output Driver.")
            d = drivers[0]
            if flt(d.qty_per_person) <= 0:
                frappe.throw(f"Row #{d.idx}: Qty For Recipe Basis is required for Output Driver.")
            if flt(d.qty_per_output) <= 0:
                frappe.throw(f"Row #{d.idx}: Qty Per Output is required for Output Driver.")
            if not d.uom:
                frappe.throw(f"Row #{d.idx}: UOM is required for Output Driver.")
        elif method == "Sum Output Materials":
            rows = [r for r in (self.materials or []) if cint(r.include_in_output_qty)]
            if not rows:
                frappe.throw("At least one material must be marked Include in Output Qty.")
            uoms = list(set([r.uom for r in rows if r.uom]))
            if len(uoms) != 1:
                frappe.throw("All Include in Output Qty material rows must have the same UOM.")
            if flt(self.output_container_capacity_qty) <= 0 or not self.output_container_capacity_uom:
                frappe.throw("Output Container Capacity Qty and UOM are required for Sum Output Materials.")

    def validate_materials(self):
        for row in self.materials or []:
            if not row.material_item:
                frappe.throw(f"Row #{row.idx}: Material Item is required.")
            base = row.material__calculation_base or "Per Person"
            if base not in ["Per Person", "Per Output", "Output Driver", "Manual"]:
                frappe.throw(f"Row #{row.idx}: Invalid Material Calculation Base: {base}")
            if base != "Manual" and not row.uom:
                frappe.throw(f"Row #{row.idx}: UOM is required.")
            if base == "Per Person" and flt(row.qty_per_person) <= 0:
                frappe.throw(f"Row #{row.idx}: Qty For Recipe Basis is required for Per Person material.")
            if base == "Per Output" and flt(row.qty_per_output) <= 0:
                frappe.throw(f"Row #{row.idx}: Qty Per Output is required for Per Output material.")
            if base == "Output Driver":
                if flt(row.qty_per_person) <= 0:
                    frappe.throw(f"Row #{row.idx}: Qty For Recipe Basis is required for Output Driver material.")
                if flt(row.qty_per_output) <= 0:
                    frappe.throw(f"Row #{row.idx}: Qty Per Output is required for Output Driver material.")
            self.validate_receiving_row(row)

    def validate_receiving_row(self, row):
        if not cint(row.include_in_purchase):
            return
        mode = row.receiving_mode or "Single Unit"
        if mode not in ["Single Unit", "Unit Breakdown", "Small Qty Rule", "No Receiving"]:
            frappe.throw(f"Row #{row.idx}: Invalid Receiving Mode: {mode}")
        if mode == "No Receiving":
            return
        if mode == "Single Unit":
            if flt(row.receiving_capacity_qty) <= 0 or not row.receiving_capacity_uom:
                frappe.throw(f"Row #{row.idx}: Receiving Capacity Qty and UOM are required.")
        elif mode == "Unit Breakdown":
            if flt(row.large_pack_qty) <= 0 or not row.large_pack_uom:
                frappe.throw(f"Row #{row.idx}: Large Pack Qty and UOM are required for Unit Breakdown.")
            if flt(row.small_pack_qty) <= 0 or not row.small_pack_uom:
                frappe.throw(f"Row #{row.idx}: Small Pack Qty and UOM are required for Unit Breakdown.")
        elif mode == "Small Qty Rule":
            if flt(row.receiving_capacity_qty) <= 0 or not row.receiving_capacity_uom:
                frappe.throw(f"Row #{row.idx}: Receiving Capacity Qty and UOM are required for Small Qty Rule.")
            if flt(row.small_qty_threshold_percent) <= 0 or not row.small_qty_uom:
                frappe.throw(f"Row #{row.idx}: Small Qty Threshold Percent and Small Qty UOM are required for Small Qty Rule.")

    def validate_run_setup(self):
        if not self.default_workstation and not self.workstation_calculation_method and flt(self.workstation_load_qty) <= 0:
            return
        if flt(self.workstation_load_qty) > 0 and not self.workstation_load_uom:
            frappe.throw("Run Load UOM is required when Run Load Qty is entered.")
        if self.workstation_load_uom and flt(self.workstation_load_qty) <= 0:
            frappe.throw("Run Load Qty is required when Run Load UOM is entered.")
        if flt(self.workstation_load_qty) > 0 and not self.workstation_calculation_method:
            frappe.throw("Run Calculation Base is required when Run Load Qty is entered.")

    def apply_rounding(self, value, method):
        value = flt(value)
        if method == "No Rounding":
            return value
        if method == "Round Down":
            return int(value)
        if method == "Half Round":
            return round(value)
        rounded = int(value)
        return rounded + 1 if value > rounded else rounded
