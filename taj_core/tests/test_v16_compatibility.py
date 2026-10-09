"""Frappe v16 API-contract regressions, isolated from a live database.

These tests execute selected real override functions with stubbed dependencies,
so the tests can run without SSH or a production database. They do not replace
Frappe bench integration tests.
"""

from __future__ import annotations

import ast
import copy
import datetime
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


APP_ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, field):
        try:
            return self[field]
        except KeyError as exc:
            raise AttributeError(field) from exc

    def __setattr__(self, field, value):
        self[field] = value


def isolated_definition(filename, name, env, *, member=None):
    """Compile only one actual source definition using explicit safe stubs."""
    path = APP_ROOT / "overrides" / filename
    source = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    node = copy.deepcopy(node)
    if member:
        node.body = [next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == member)]
    tree = ast.fix_missing_locations(
        ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node],
            type_ignores=[],
        )
    )
    space = dict(env)
    exec(compile(tree, str(path), "exec"), space)
    return space[name]


class TestLeaveApplicationV16(unittest.TestCase):
    def setUp(self):
        self.custom = True
        self.core = SimpleNamespace(
            get_number_of_leave_days=Mock(return_value=3.0),
            get_leave_balance_on=Mock(return_value={"leave_balance_for_consumption": 10.0}),
            validate_leave_access=Mock(),
            is_lwp=Mock(return_value=False),
        )
        self.calc = Mock(return_value=2.0)
        self.frappe = SimpleNamespace(
            whitelist=lambda: (lambda fn: fn),
            db=SimpleNamespace(get_single_value=lambda *args: 2),
            throw=lambda msg: (_ for _ in ()).throw(ValueError(msg)),
        )
        self.env = dict(
            frappe=self.frappe,
            datetime=datetime,
            core_leave_application=self.core,
            _use_taj_public_holiday_policy=lambda leave_type: self.custom,
            _compute_taj_public_holiday_leave_days=self.calc,
            cint=int,
            flt=lambda value, precision=2: round(float(value), int(precision)),
            _=lambda s: s,
        )

    def test_custom_policy_enforces_permission_and_accepts_v16_kwarg(self):
        fn = isolated_definition("leave_application.py", "get_number_of_leave_days", self.env)
        result = fn("EMP-1", "Leave Type", "2026-10-01", "2026-10-03", leave_application="LEAVE-1")
        self.assertEqual(result, 2.0)
        self.core.validate_leave_access.assert_called_once_with("EMP-1", "LEAVE-1")
        self.calc.assert_called_once()

    def test_custom_policy_denies_before_calculating(self):
        fn = isolated_definition("leave_application.py", "get_number_of_leave_days", self.env)
        self.core.validate_leave_access.side_effect = PermissionError("Not permitted")
        with self.assertRaises(PermissionError):
            fn("EMP-1", "Leave Type", "2026-10-01", "2026-10-03")
        self.calc.assert_not_called()

    def test_standard_policy_preserves_standard_handler_and_v16_context(self):
        self.custom = False
        fn = isolated_definition("leave_application.py", "get_number_of_leave_days", self.env)
        result = fn("EMP-1", "Leave Type", "2026-10-01", "2026-10-03", leave_application="LEAVE-1")
        self.assertEqual(result, 3.0)
        self.core.get_number_of_leave_days.assert_called_once()
        self.assertEqual(self.core.get_number_of_leave_days.call_args.kwargs["leave_application"], "LEAVE-1")
        self.calc.assert_not_called()

    def _leave_document(self, *, is_new):
        class StandardLeave:
            def validate_balance_leaves(self):
                return "standard"

        cls = isolated_definition("leave_application.py", "LeaveApplication", {
            **self.env, "HRMSLeaveApplication": StandardLeave
        }, member="validate_balance_leaves")
        doc = cls()
        doc.leave_type = "Leave Type"
        doc.employee = "EMP-1"
        doc.from_date = "2026-10-01"
        doc.to_date = "2026-10-03"
        doc.half_day = 0
        doc.half_day_date = None
        doc.name = "LEAVE-1"
        doc.is_new = lambda: is_new
        doc.status = "Open"
        doc.show_insufficient_balance_message = Mock()
        return doc

    def test_existing_leave_document_passes_its_id_to_balance_check(self):
        doc = self._leave_document(is_new=False)
        doc.validate_balance_leaves()
        self.assertEqual(self.core.get_leave_balance_on.call_args.kwargs["leave_application"], "LEAVE-1")

    def test_new_leave_document_does_not_claim_existing_record_access(self):
        doc = self._leave_document(is_new=True)
        doc.validate_balance_leaves()
        self.assertIsNone(self.core.get_leave_balance_on.call_args.kwargs["leave_application"])

    def test_standard_leave_document_still_uses_parent_validation(self):
        self.custom = False
        doc = self._leave_document(is_new=True)
        self.assertEqual(doc.validate_balance_leaves(), "standard")
        self.core.get_leave_balance_on.assert_not_called()


class FakeProductionPlan:
    def __init__(self):
        self._tables = {}
        self.po_items = []
        self.skip_available_sub_assembly_item = 0
        self.sub_assembly_warehouse = "Raw Materials - Taj"
        self.company = "Taj"
        self.combine_sub_items = 0
        self.supplier_set = False

    def set(self, field, value):
        self._tables[field] = value

    def get(self, field):
        return self._tables.get(field, [])

    def append(self, field, row):
        row = Row(row)
        if not row.get("name") or str(row.get("name")).startswith("TMP-"):
            row.name = f"ROW-{len(self.get(field)) + 1}"
        self._tables.setdefault(field, []).append(row)
        return row

    def set_sub_assembly_items_based_on_level(self, source, bom_data, manufacturing_type):
        for row in bom_data:
            row.type_of_manufacturing = manufacturing_type or "In House"
            row.fg_warehouse = "WIP - Taj"

    def combine_subassembly_items(self, records):
        return records

    def set_default_supplier_for_subcontracting_order(self):
        self.supplier_set = True


class TestProductionPlanV16(unittest.TestCase):
    def setUp(self):
        self.tracked = set()
        self.built = []
        self.messages = []
        self.row_counter = 0

        def build(_, bin_details, bom_no, bom_data, planned_qty, company, **kwargs):
            self.built.append(bom_no)
            if bom_no != "BOM-EMPTY":
                bom_data.append(Row(production_item=f"SUB-{bom_no}", bom_no=bom_no,
                                    stock_qty=4.0, qty=4.0, type_of_manufacturing="In House",
                                    fg_warehouse="WIP - Taj"))

        self.frappe = SimpleNamespace(
            whitelist=lambda: (lambda fn: fn),
            _dict=Row,
            db=SimpleNamespace(get_value=lambda dt, doc, field: int(doc in self.tracked)),
            generate_hash=lambda **kwargs: "testhash00",
            msgprint=lambda msg, **kwargs: self.messages.append(str(msg)),
            throw=lambda msg: (_ for _ in ()).throw(ValueError(msg)),
        )
        self.cls = isolated_definition("production_plan.py", "CustomProductionPlan", dict(
            frappe=self.frappe, _=lambda x: x, flt=float,
            ERPNextProductionPlan=FakeProductionPlan, build_sub_assembly_items=build
        ))

    def make_row(self, bom, idx):
        return Row(name=f"PLAN-ROW-{idx}", item_code=f"FG-{idx}", bom_no=bom, idx=idx, planned_qty=5)

    def test_all_tracked_boms_are_excluded_without_available_stock_notice(self):
        doc = self.cls()
        self.tracked.add("BOM-TRACKED")
        doc.skip_available_sub_assembly_item = 1
        doc.po_items = [self.make_row("BOM-TRACKED", 1)]
        doc.get_sub_assembly_items()
        self.assertEqual(self.built, [])
        self.assertEqual(doc.get("sub_assembly_items"), [])
        self.assertEqual(doc.get(doc.SPLIT_FIELD), [])
        self.assertEqual(len(self.messages), 1)
        self.assertIn("Track Semi Finished Goods", self.messages[0])

    def test_mixed_tracked_and_regular_bom_keeps_split_links(self):
        doc = self.cls()
        self.tracked.add("BOM-TRACKED")
        doc.po_items = [self.make_row("BOM-TRACKED", 1), self.make_row("BOM-REGULAR", 2)]
        doc.get_sub_assembly_items()
        self.assertEqual(self.built, ["BOM-REGULAR"])
        self.assertEqual(len(doc.get("sub_assembly_items")), 1)
        splits = doc.get(doc.SPLIT_FIELD)
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0].source_assembly_item, "PLAN-ROW-2")
        self.assertEqual(splits[0].source_sub_assembly_item, doc.get("sub_assembly_items")[0].name)
        self.assertTrue(doc.supplier_set)

    def test_regular_bom_with_no_available_subassembly_keeps_stock_notice(self):
        doc = self.cls()
        doc.skip_available_sub_assembly_item = 1
        doc.po_items = [self.make_row("BOM-EMPTY", 1)]
        doc.get_sub_assembly_items()
        self.assertIn("sufficient Sub Assembly Items", " ".join(self.messages))


class FakePick:
    def __init__(self, manual):
        self.pick_manually = manual
        self.locations_calls = 0

    def set_item_locations(self):
        self.locations_calls += 1


class TestPickListV16(unittest.TestCase):
    def setUp(self):
        self.pick = FakePick(manual=True)
        self.mapping = None
        self.locations = []

        def get_value(dt, name, field):
            if (dt, field) == ("Work Order", "qty"):
                return 10
            if (dt, field) == ("Work Order", "company"):
                return "Taj"
            if (dt, field) == ("Warehouse", "company"):
                return "Taj"
            return None

        def get_all(dt, **kwargs):
            if dt == "Work Order Item":
                return ["RM-1", "SUB-1"]
            if dt == "BOM":
                return ["SUB-1"]
            return []

        self.frappe = SimpleNamespace(
            whitelist=lambda: (lambda fn: fn),
            db=SimpleNamespace(get_value=get_value, get_single_value=lambda *args: "Raw Materials - Taj"),
            get_all=get_all,
            get_value=get_value,
            throw=lambda msg: (_ for _ in ()).throw(ValueError(msg)),
        )

        def mapped(doctype, name, mapping, target_doc):
            self.mapping = mapping
            return self.pick

        self.fn = isolated_definition("work_order.py", "create_pick_list", dict(
            frappe=self.frappe, json=json, flt=float, get_mapped_doc=mapped
        ))

    def test_manual_pick_does_not_force_auto_location_assignment(self):
        result = self.fn("WO-1", for_qty=5, target_doc='{"for_qty": 5}')
        self.assertIs(result, self.pick)
        self.assertEqual(self.pick.locations_calls, 0)
        self.assertEqual(result.parent_warehouse, "Raw Materials - Taj")

    def test_automatic_pick_still_resolves_locations(self):
        self.pick.pick_manually = False
        self.fn("WO-1", for_qty=5, target_doc='{"for_qty": 5}')
        self.assertEqual(self.pick.locations_calls, 1)

    def test_pick_mapping_keeps_v16_unmapped_transferred_quantity(self):
        self.fn("WO-1", for_qty=5, target_doc='{"for_qty": 5}')
        mapping = self.mapping["Work Order Item"]
        self.assertIn("transferred_qty", mapping["field_no_map"])
        cond = mapping["condition"]
        self.assertTrue(cond(Row(transferred_qty=0, required_qty=3, item_code="RM-1")))
        self.assertFalse(cond(Row(transferred_qty=0, required_qty=3, item_code="SUB-1")))


if __name__ == "__main__":
    unittest.main()
