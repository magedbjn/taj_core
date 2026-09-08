import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def read(relpath):
    return (PACKAGE_ROOT / relpath).read_text()


def function_source(relpath, function_name):
    import ast

    source = read(relpath)
    tree = ast.parse(source)
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"{function_name} not found in {relpath}")


class TestRemainingHighAuditFixes(TestCase):
    def test_h06_final_trial_uses_transaction_locks(self):
        source = function_source(
            "rnd/doctype/product_proposal_trial/product_proposal_trial.py",
            "validate_final_trial",
        )
        self.assertIn("`tabProduct Proposal`", source)
        self.assertIn("`tabProduct Proposal Trial`", source)
        self.assertGreaterEqual(source.lower().count("for update"), 2)

    def test_h07_bom_trial_source_is_validated_on_server(self):
        hooks = read("hooks.py")
        source = function_source(
            "rnd/doctype/product_proposal_trial/product_proposal_trial.py",
            "validate_bom_trial_source",
        )
        self.assertIn("validate_bom_trial_source", hooks)
        self.assertIn('proposal.check_permission("read")', source)
        self.assertIn('trial.check_permission("read")', source)
        self.assertIn("trial.product_proposal", source)
        self.assertIn('trial.status != "Approved"', source)
        self.assertIn("proposal_item", source)
        self.assertIn("bom_item", source)

    def test_h08_split_rm_rows_preserve_group_total(self):
        from taj_core.overrides.work_order import rebuild_manufacture_rm_rows

        work_order = SimpleNamespace(
            required_items=[
                frappe._dict(
                    item_code="RM",
                    original_item=None,
                    source_warehouse="WIP",
                    required_qty=10,
                    include_item_in_manufacturing=1,
                )
            ]
        )
        entry = SimpleNamespace(
            items=[
                frappe._dict(item_code="RM", s_warehouse="WIP", qty=6, transfer_qty=6),
                frappe._dict(item_code="RM", s_warehouse="WIP", qty=4, transfer_qty=4),
            ]
        )

        rebuild_manufacture_rm_rows(entry, work_order)

        self.assertEqual([row.qty for row in entry.items], [6, 4])
        self.assertEqual(sum(row.qty for row in entry.items), 10)

    def test_h09_partial_expense_payment_does_not_mark_paid(self):
        from taj_core.custom import expenses_claim as module

        claim = SimpleNamespace(
            name="EC-TEST",
            workflow_state="Unpaid",
            owner="owner@example.com",
        )

        with (
            patch.object(module, "_get_related_expense_claims", return_value=["EC-TEST"]),
            patch.object(module.frappe, "get_doc", return_value=claim),
            patch.object(module, "get_outstanding_amount_for_claim", return_value=900),
            patch.object(module, "_apply_transition_to_state") as transition,
            patch.object(module.frappe, "log_error"),
        ):
            module.update_expense_claim_status_on_payment(
                SimpleNamespace(doctype="Payment Entry", name="PE-TEST"),
                None,
            )

        transition.assert_not_called()

    def test_h10_bulk_return_cancel_requires_free_capacity(self):
        from taj_core.catering.doctype.catering_equipment_return import (
            catering_equipment_return as module,
        )
        from taj_core.catering.doctype.catering_equipment_delivery import (
            catering_equipment_delivery as delivery_module,
        )

        doc = SimpleNamespace(
            items=[
                frappe._dict(
                    equipment="EQ-TEST",
                    has_serial_no=0,
                    return_qty=10,
                )
            ]
        )

        with (
            patch.object(delivery_module, "_lock_equipment_for_update", return_value=10),
            patch.object(delivery_module, "_get_available_qty_current", return_value=0),
        ):
            with self.assertRaises(frappe.ValidationError):
                module.CateringEquipmentReturn.validate_bulk_cancel_capacity(doc)

    def test_h11_temperature_range_does_not_use_undefined_value(self):
        source = function_source(
            "taj_core/page/job_card_board/job_card_board.py",
            "board_complete_job",
        )
        self.assertIn("temp_val = None", source)
        self.assertIn("requires_temperature", source)
        self.assertIn("temp_val is not None", source)

    def test_h12_finished_bundle_batches_are_supported(self):
        from taj_core.company_documents.report.raw_material_traceability import (
            raw_material_traceability as module,
        )

        row = frappe._dict(
            direct_finished_batch=None,
            finished_serial_and_batch_bundle="FG-BUNDLE",
        )
        with patch.object(
            module,
            "get_serial_batch_bundle_data",
            return_value=[
                {"batch_no": "FG-01", "qty": 6},
                {"batch_no": "FG-02", "qty": 4},
            ],
        ):
            allocations = module._get_finished_batch_allocations(row)

        self.assertEqual(allocations, [("FG-01", 0.6), ("FG-02", 0.4)])
        source = function_source(
            "company_documents/report/raw_material_traceability/raw_material_traceability.py",
            "get_data",
        )
        self.assertIn("sbe_finished.batch_no", source)

    def test_h13_transfer_for_manufacture_is_not_consumption(self):
        from taj_core.qc.report.batch_traceability import batch_traceability as module

        documents = {
            "TRANSFER": SimpleNamespace(
                purpose="Material Transfer for Manufacture",
                items=[frappe._dict(item_code="RM", batch_no="BATCH", qty=10, s_warehouse="WH")],
            ),
            "CONSUME": SimpleNamespace(
                purpose="Manufacture",
                items=[frappe._dict(item_code="RM", batch_no="BATCH", qty=10, s_warehouse="WH")],
            ),
        }

        with (
            patch.object(module.frappe, "get_all", return_value=list(documents)),
            patch.object(module.frappe, "get_doc", side_effect=lambda dt, name: documents[name]),
        ):
            result = module.get_consumed_batches_from_work_order("WO-TEST")

        self.assertEqual(result["RM"][0]["qty"], 10)

    def test_h14_read_endpoints_apply_permissions(self):
        steamer = function_source("api/steamer_labels.py", "get_label_html")
        catering_centers = function_source(
            "catering/doctype/catering_buffet_requirement/catering_buffet_requirement.py",
            "get_catering_centers_for_year",
        )
        catering_plan = function_source(
            "catering/doctype/catering_buffet_requirement/catering_buffet_requirement.py",
            "get_buffet_plan",
        )
        product_query = function_source(
            "rnd/doctype/product_development/product_development.py",
            "product_name_distinct_query",
        )
        plan_query = function_source(
            "taj_core/report/production_plan_period_hierarchy/production_plan_period_hierarchy.py",
            "production_plan_query",
        )
        subassembly = function_source(
            "taj_core/report/production_plan_period_hierarchy/production_plan_period_hierarchy.py",
            "get_sub_assembly_item_options",
        )

        self.assertIn('check_permission("read")', steamer)
        self.assertIn("frappe.get_list", catering_centers)
        self.assertIn('check_permission("read")', catering_plan)
        self.assertIn("frappe.get_list", product_query)
        self.assertIn("frappe.get_list", plan_query)
        self.assertIn('plan.check_permission("read")', subassembly)

    def test_h15_material_request_does_not_merge_distinct_plan_sources(self):
        from taj_core.custom import material_request as module

        rows = [
            frappe._dict(
                item_code="RM",
                warehouse="WH",
                from_warehouse=None,
                uom="Kg",
                conversion_factor=1,
                schedule_date="2026-09-08",
                qty=5,
                stock_qty=5,
                production_plan="PP-A",
                production_plan_item="A",
            ),
            frappe._dict(
                item_code="RM",
                warehouse="WH",
                from_warehouse=None,
                uom="Kg",
                conversion_factor=1,
                schedule_date="2026-09-08",
                qty=3,
                stock_qty=3,
                production_plan="PP-B",
                production_plan_item="B",
            ),
        ]

        class FakeDoc:
            docstatus = 0

            def __init__(self):
                self.items = rows

            def remove(self, row):
                self.items.remove(row)

            def save(self):
                pass

            def as_dict(self):
                return {"items": self.items}

        doc = FakeDoc()
        with (
            patch.object(module.frappe, "get_doc", return_value=doc),
            patch.object(module.frappe, "msgprint"),
            patch.object(module.frappe, "log_error"),
        ):
            result = module.collect_similar_items("MR-TEST")

        self.assertEqual(len(result["items"]), 2)

    def test_h16_checklist_roles_match_runtime_permissions(self):
        admin = json.loads(read("checklist/page/checklist_admin/checklist_admin.json"))
        user = json.loads(read("checklist/page/checklist_user/checklist_user.json"))
        answer = json.loads(read("checklist/doctype/checklist_answer/checklist_answer.json"))

        admin_roles = {row["role"] for row in admin["roles"]}
        user_roles = {row["role"] for row in user["roles"]}
        answer_perms = {row["role"]: row for row in answer["permissions"]}

        self.assertIn("Checklist Manager", admin_roles)
        self.assertIn("Checklist Manager", user_roles)
        self.assertIn("Employee", user_roles)
        self.assertEqual(answer_perms["Employee"].get("read"), 1)
        self.assertEqual(answer_perms["Checklist Manager"].get("read"), 1)


class TestRemainingMediumAuditFixes(TestCase):
    def test_m01_leave_query_uses_date_overlap(self):
        source = function_source(
            "peopleops/report/employee_first_last_checkins/employee_first_last_checkins.py",
            "get_leave_map_per_employee",
        )
        self.assertIn("LeaveApplication.from_date <= month_end", source)
        self.assertIn("LeaveApplication.to_date >= month_start", source)

    def test_m02_overtime_validates_full_interval_against_now(self):
        source = function_source(
            "peopleops/doctype/department_overtime_request/department_overtime_request.py",
            "_validate_not_future",
        )
        self.assertNotIn("if row_date == today", source)
        self.assertIn("end and end > now_dt", source)

    def test_m03_delivered_status_is_set_before_submit(self):
        before_submit = function_source(
            "catering/doctype/catering_equipment_delivery/catering_equipment_delivery.py",
            "before_submit",
        )
        on_submit = function_source(
            "catering/doctype/catering_equipment_delivery/catering_equipment_delivery.py",
            "on_submit",
        )
        self.assertIn('self.status = "Delivered"', before_submit)
        self.assertNotIn('self.status = "Delivered"', on_submit)

    def test_m04_bom_cycle_detection_uses_current_path_copy(self):
        tree_source = function_source(
            "qc/report/batch_traceability/batch_traceability.py",
            "explode_bom_tree",
        )
        table_source = function_source(
            "qc/report/batch_traceability/batch_traceability.py",
            "explode_bom_level_order",
        )
        self.assertIn("visited = set(visited or set())", tree_source)
        self.assertIn("visited = set(visited or set())", table_source)

    def test_m05_unimplemented_report_is_not_exposed(self):
        report = json.loads(
            read(
                "engineering/report/monthly_consumption_comparison/"
                "monthly_consumption_comparison.json"
            )
        )
        self.assertEqual(report.get("disabled"), 1)
