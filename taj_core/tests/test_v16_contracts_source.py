"""Dependency-free source contract checks for Taj Core on Frappe/ERPNext/HRMS v16.

These tests do not contact a site, execute migrations or modify any documents.
Runtime behaviour also needs verification with an installed v16 site.
"""

import ast
import unittest
from pathlib import Path


OVERRIDES = Path(__file__).resolve().parents[1] / "overrides"


def source_of(path, function, class_name=None):
    source = (OVERRIDES / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if class_name:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                nodes = node.body
                break
        else:
            nodes = tree.body
            break
    else:
        raise AssertionError(f"Missing class: {class_name}")
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return node, ast.get_source_segment(source, node)
    raise AssertionError(f"Missing function: {function}")


def kwarg_names(function_node):
    return {arg.arg for arg in function_node.args.args + function_node.args.kwonlyargs}


class TestLeaveV16Contracts(unittest.TestCase):
    def test_public_leave_api_accepts_record_context(self):
        func, source = source_of("leave_application.py", "get_number_of_leave_days")
        self.assertIn("leave_application", kwarg_names(func))

    def test_custom_policy_validates_access_prior_to_calculation(self):
        func, source = source_of("leave_application.py", "get_number_of_leave_days")
        access = source.index("core_leave_application.validate_leave_access(")
        calc = source.index("return _compute_taj_public_holiday_leave_days(")
        self.assertLess(access, calc)

    def test_standard_path_passes_leave_application_to_hrms(self):
        _, source = source_of("leave_application.py", "get_number_of_leave_days")
        self.assertIn("leave_application=leave_application", source)

    def test_balance_validation_passes_context_to_hrms(self):
        _, source = source_of("leave_application.py", "validate_balance_leaves", "LeaveApplication")
        self.assertIn("leave_application = None if self.is_new() else self.name", source)
        self.assertIn("leave_application=leave_application", source)

    def test_custom_attendance_policy_still_exists(self):
        _, source = source_of("leave_application.py", "update_attendance", "LeaveApplication")
        self.assertIn("public_holiday_dates", source)
        self.assertIn("create_or_update_attendance", source)


class TestProductionPlanV16Contracts(unittest.TestCase):
    def test_tracked_bom_is_skipped_before_subassembly_builder(self):
        _, source = source_of("production_plan.py", "get_sub_assembly_items", "CustomProductionPlan")
        guard = source.index('frappe.db.get_value("BOM", row.bom_no, "track_semi_finished_goods")')
        builder = source.index("build_sub_assembly_items(")
        self.assertLess(guard, builder)
        self.assertIn("continue", source[guard:builder])

    def test_tracked_only_does_not_raise_no_stock_notice(self):
        _, source = source_of("production_plan.py", "get_sub_assembly_items", "CustomProductionPlan")
        self.assertIn("not track_semi_finished_goods", source)

    def test_subassembly_split_and_final_link_preserved(self):
        _, source = source_of("production_plan.py", "get_sub_assembly_items", "CustomProductionPlan")
        self.assertIn("_append_split_row(", source)
        self.assertIn("_link_split_rows_to_final_rows(", source)
        self.assertIn("set_default_supplier_for_subcontracting_order()", source)


class TestPickListV16Contracts(unittest.TestCase):
    def test_transferred_qty_is_not_mapped(self):
        _, source = source_of("work_order.py", "create_pick_list")
        self.assertIn('"field_no_map": ["transferred_qty"]', source)

    def test_manual_picking_skips_automatic_location_assignment(self):
        _, source = source_of("work_order.py", "create_pick_list")
        self.assertIn("if not doc.pick_manually:", source)
        self.assertIn("doc.set_item_locations()", source)

    def test_taj_warehouse_policy_and_bom_filter_remain(self):
        _, source = source_of("work_order.py", "create_pick_list")
        self.assertIn("taj_pick_list_parent_warehouse", source)
        self.assertIn("doc.item_code not in bom_items", source)
        self.assertIn("warehouse_company != work_order_company", source)


if __name__ == "__main__":
    unittest.main()
