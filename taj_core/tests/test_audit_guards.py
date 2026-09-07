import ast
import importlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def read(relpath):
    return (PACKAGE_ROOT / relpath).read_text()


def function_source(relpath, function_name):
    path = PACKAGE_ROOT / relpath
    source = path.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) and node.name == function_name:
            lines = source.splitlines()
            return "\n".join(
                lines[node.lineno - 1 : node.end_lineno]
            )

    raise AssertionError(
        f"{function_name} not found in {relpath}"
    )


class TestHooksAndDependencies(TestCase):
    def test_required_apps_include_erpnext_and_hrms(self):
        hooks = importlib.import_module("taj_core.hooks")

        self.assertIn("erpnext", hooks.required_apps)
        self.assertIn("hrms", hooks.required_apps)

    def test_production_plan_override_is_registered(self):
        hooks = importlib.import_module("taj_core.hooks")

        self.assertEqual(
            hooks.override_doctype_class["Production Plan"],
            "taj_core.overrides.production_plan."
            "CustomProductionPlan",
        )

    def test_purchase_invoice_override_is_registered(self):
        hooks = importlib.import_module("taj_core.hooks")

        self.assertEqual(
            hooks.override_doctype_class["Purchase Invoice"],
            "taj_core.overrides.purchase_invoice."
            "TajPurchaseInvoice",
        )

    def test_old_purchase_invoice_hooks_are_removed(self):
        hooks = importlib.import_module("taj_core.hooks")
        events = hooks.doc_events.get("Purchase Invoice", {})

        self.assertNotIn("before_validate", events)
        self.assertNotIn("before_save", events)

        self.assertNotIn(
            "taj_core.custom.purchase_invoice",
            read("hooks.py"),
        )


class TestTransactionGuards(TestCase):
    def test_no_runtime_manual_commits(self):
        violations = []

        for path in PACKAGE_ROOT.rglob("*.py"):
            relative = path.relative_to(PACKAGE_ROOT)

            if "patches" in relative.parts:
                continue

            if path.name.startswith("test_"):
                continue

            tree = ast.parse(path.read_text())

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                func = node.func

                if not isinstance(func, ast.Attribute):
                    continue

                if func.attr != "commit":
                    continue

                owner = func.value

                if not (
                    isinstance(owner, ast.Attribute)
                    and owner.attr == "db"
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "frappe"
                ):
                    continue

                violations.append(
                    f"{relative}:{node.lineno}"
                )

        self.assertEqual([], violations)

    def test_supplier_group_errors_fail_closed(self):
        from taj_core.integrations import supplier_hooks

        supplier_hooks.is_qualified_supplier_group.cache_clear()

        with patch.object(
            supplier_hooks.frappe,
            "get_cached_doc",
            side_effect=RuntimeError("settings unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "settings unavailable",
            ):
                supplier_hooks.is_qualified_supplier_group(
                    "_Test Group"
                )

        supplier_hooks.is_qualified_supplier_group.cache_clear()

    def test_license_type_does_not_invent_expiry_date(self):
        from taj_core.company_documents.doctype.license_type \
            import license_type

        with patch.object(
            license_type.frappe.db,
            "sql",
        ) as sql:
            license_type.propagate_no_expiry_change(
                "Test License Type",
                0,
            )

        query, params = sql.call_args.args

        normalized = " ".join(query.split())

        self.assertIn(
            "ELSE `expiry_date`",
            normalized,
        )
        self.assertNotIn(
            "CURDATE",
            normalized.upper(),
        )
        self.assertNotIn(
            "TODAY",
            normalized.upper(),
        )
        self.assertEqual(params["new"], 0)
        self.assertEqual(
            params["lt"],
            "Test License Type",
        )


class TestSecurityGuards(TestCase):
    def test_checklist_reassign_requires_manager(self):
        source = function_source(
            "checklist/api.py",
            "get_reassign_users",
        )

        self.assertIn("_ensure_manager()", source)

    def test_preparation_label_endpoints_check_read_permission(self):
        relpath = (
            "taj_manufacturing/api/"
            "preparation_labels.py"
        )

        names = (
            "get_required_items_for_work_order",
            "render_preparation_labels_html",
            "render_preparation_labels_from_job_card",
            "get_raw_materials_from_job_card",
        )

        for name in names:
            with self.subTest(function=name):
                source = function_source(
                    relpath,
                    name,
                )
                self.assertIn(
                    'check_permission("read")',
                    source,
                )

    def test_raw_material_fallback_does_not_swallow_errors(self):
        source = function_source(
            "taj_manufacturing/api/"
            "preparation_labels.py",
            "get_raw_materials_from_job_card",
        )

        tree = ast.parse(source)
        swallowed = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue

            is_exception = (
                isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            )

            only_pass = (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
            )

            if is_exception and only_pass:
                swallowed.append(node.lineno)

        self.assertEqual([], swallowed)

    def test_catering_return_checks_delivery_permission(self):
        source = function_source(
            "catering/doctype/"
            "catering_equipment_return/"
            "catering_equipment_return.py",
            "get_delivery_items",
        )

        self.assertIn(
            'check_permission("read")',
            source,
        )


class TestSchemaAndMigrationGuards(TestCase):
    def test_rnd_settings_is_single_and_has_required_fields(self):
        data = json.loads(
            read(
                "rnd/doctype/rnd_settings/"
                "rnd_settings.json"
            )
        )

        self.assertEqual(data["issingle"], 1)

        fields = {
            row["fieldname"]
            for row in data["fields"]
        }

        self.assertTrue(
            {
                "item_naming_series",
                "default_item_group",
                "stock_uom",
                "default_brand",
                "shelf_life_in_days",
                "default_warehouse",
            }.issubset(fields)
        )

    def test_manufacturing_settings_has_pick_list_warehouse(self):
        data = json.loads(
            read("fixtures/manufacturing_settings.json")
        )

        fields = {
            row.get("fieldname")
            for row in data
        }

        self.assertIn(
            "taj_pick_list_parent_warehouse",
            fields,
        )

    def test_sensory_status_typo_is_gone(self):
        offenders = []

        old_value = re.compile(
            r"(?<![A-Za-z])"
            r"Need Improvemen"
            r"(?![A-Za-z])"
        )

        for path in (
            PACKAGE_ROOT / "rnd"
        ).rglob("*"):
            if not path.is_file():
                continue

            if path.suffix not in {".py", ".json", ".js"}:
                continue

            if old_value.search(path.read_text()):
                offenders.append(
                    str(path.relative_to(PACKAGE_ROOT))
                )

        self.assertEqual([], offenders)

    def test_raw_material_specification_is_unique_by_item(self):
        data = json.loads(
            read(
                "qc/doctype/"
                "raw_material_specification/"
                "raw_material_specification.json"
            )
        )

        self.assertEqual(
            data.get("autoname"),
            "field:item_code",
        )

        item_code = next(
            row
            for row in data["fields"]
            if row.get("fieldname") == "item_code"
        )

        self.assertEqual(
            item_code.get("unique"),
            1,
        )

    def test_checklist_answer_question_field_order_is_complete(self):
        candidates = []

        for path in (
            PACKAGE_ROOT / "checklist"
        ).rglob("*.json"):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue

            if data.get("name") == "Checklist Answer Question":
                candidates.append(data)

        self.assertEqual(len(candidates), 1)

        field_order = candidates[0]["field_order"]

        required = {
            "question",
            "type",
            "yes_no_answer",
            "int_answer",
            "float_answer",
            "select_answer",
            "answer_select_options",
            "answer",
            "has_issue",
            "issue_note",
        }

        self.assertTrue(
            required.issubset(set(field_order))
        )

    def test_only_one_production_plan_split_doctype_exists(self):
        matches = []

        for path in PACKAGE_ROOT.rglob("*.json"):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            if (
                data.get("name")
                == "Production Plan Sub Assembly Split"
            ):
                matches.append(path)

        self.assertEqual(len(matches), 1)

    def test_maintenance_contract_updates_visits_count(self):
        from taj_core.engineering.doctype \
            .maintenance_contract.maintenance_contract \
            import MaintenanceContract

        fake = SimpleNamespace(
            total_visits=3,
            maintenance_visit=[
                SimpleNamespace(),
                SimpleNamespace(),
            ],
            visits_count=0,
        )

        MaintenanceContract.validate_visits(fake)

        self.assertEqual(fake.visits_count, 2)

    def test_product_development_fallback_has_same_filters(self):
        source = function_source(
            "rnd/doctype/product_development/"
            "product_development.py",
            "product_name_distinct_query",
        )

        self.assertGreaterEqual(
            source.count("is_default = 1"),
            2,
        )

        self.assertGreaterEqual(
            source.count(
                "sensory_decision != 'Reject'"
            ),
            2,
        )

    def test_rms_flag_is_restored(self):
        source = read(
            "qc/doctype/"
            "raw_material_specification/"
            "raw_material_specification.py"
        )

        self.assertIn(
            "in_rms_update",
            source,
        )
        self.assertIn(
            "finally:",
            source,
        )


class TestDeadCodeAndTypoGuards(TestCase):
    def test_finish_button_marker_is_gone(self):
        self.assertNotIn(
            "taj_from_finish_button",
            read("overrides/work_order.py"),
        )

    def test_job_card_posting_date_typo_is_gone(self):
        source = read(
            "taj_core/page/job_card_board/"
            "job_card_board.py"
        )

        self.assertNotIn(
            "psoting_date",
            source,
        )

    def test_old_checklist_typo_file_is_absent(self):
        path = (
            PACKAGE_ROOT
            / "checklist/doctype/"
            "checklist_question_template/"
            "checklist_qestion_template.json"
        )

        self.assertFalse(path.exists())


class TestSchedulerGuards(TestCase):
    def test_certificate_scheduler_is_not_whitelisted(self):
        source = read(
            "qc/doctype/supplier_qualification/"
            "supplier_qualification.py"
        )

        pattern = re.compile(
            r"@frappe\.whitelist\([^)]*\)\s*"
            r"def\s+update_certificate_statuses"
            r"|"
            r"@frappe\.whitelist\(\)\s*"
            r"def\s+update_certificate_statuses"
            r"|"
            r"@frappe\.whitelist\s*"
            r"def\s+update_certificate_statuses"
        )

        self.assertIsNone(pattern.search(source))
