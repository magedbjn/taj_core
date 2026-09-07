from unittest import TestCase

import frappe


class TestLiveOverrideIntegration(TestCase):
    def test_live_override_hooks_are_registered(self):
        hooks = frappe.get_hooks(
            "override_doctype_class"
        )

        purchase_invoice_hooks = hooks.get(
            "Purchase Invoice",
            [],
        )
        production_plan_hooks = hooks.get(
            "Production Plan",
            [],
        )

        if isinstance(purchase_invoice_hooks, str):
            purchase_invoice_hooks = [
                purchase_invoice_hooks
            ]

        if isinstance(production_plan_hooks, str):
            production_plan_hooks = [
                production_plan_hooks
            ]

        self.assertEqual(
            purchase_invoice_hooks,
            [
                "taj_core.overrides.purchase_invoice."
                "TajPurchaseInvoice"
            ],
        )

        self.assertEqual(
            production_plan_hooks,
            [
                "taj_core.overrides.production_plan."
                "CustomProductionPlan"
            ],
        )

    def test_purchase_invoice_override_imports(self):
        cls = frappe.get_attr(
            "taj_core.overrides.purchase_invoice."
            "TajPurchaseInvoice"
        )

        from erpnext.accounts.doctype.purchase_invoice \
            .purchase_invoice import PurchaseInvoice

        self.assertTrue(
            issubclass(cls, PurchaseInvoice)
        )

    def test_production_plan_override_imports(self):
        cls = frappe.get_attr(
            "taj_core.overrides.production_plan."
            "CustomProductionPlan"
        )

        from erpnext.manufacturing.doctype.production_plan \
            .production_plan import ProductionPlan

        self.assertTrue(
            issubclass(cls, ProductionPlan)
        )


class TestLiveSchedulerIntegration(TestCase):
    def test_all_taj_core_scheduler_methods_resolve(self):
        scheduler = frappe.get_hooks(
            "scheduler_events"
        )

        methods = []

        def collect(value):
            if isinstance(value, str):
                methods.append(value)

            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)

        collect(scheduler)

        taj_methods = [
            method
            for method in methods
            if method.startswith("taj_core.")
        ]

        self.assertTrue(
            taj_methods,
            "No Taj Core scheduler methods registered",
        )

        unresolved = []

        for method in taj_methods:
            try:
                frappe.get_attr(method)
            except Exception as exc:
                unresolved.append(
                    f"{method}: {exc}"
                )

        self.assertEqual(
            [],
            unresolved,
        )


class TestLiveConfigurationIntegration(TestCase):
    def test_rnd_settings_is_installed(self):
        meta = frappe.get_meta(
            "RND Settings"
        )

        self.assertTrue(meta.issingle)

        required = {
            "item_naming_series",
            "default_item_group",
            "stock_uom",
            "default_brand",
            "shelf_life_in_days",
            "default_warehouse",
        }

        actual = {
            field.fieldname
            for field in meta.fields
        }

        self.assertTrue(
            required.issubset(actual)
        )

    def test_rnd_settings_have_runtime_values(self):
        settings = frappe.get_single(
            "RND Settings"
        )

        required_values = (
            "item_naming_series",
            "default_item_group",
            "stock_uom",
            "default_brand",
            "default_warehouse",
        )

        missing = [
            field
            for field in required_values
            if not getattr(
                settings,
                field,
                None,
            )
        ]

        self.assertEqual(
            [],
            missing,
        )

    def test_manufacturing_pick_list_setting_exists(self):
        meta = frappe.get_meta(
            "Manufacturing Settings"
        )

        self.assertTrue(
            meta.has_field(
                "taj_pick_list_parent_warehouse"
            )
        )

    def test_manufacturing_pick_list_warehouse_configured(self):
        value = frappe.db.get_single_value(
            "Manufacturing Settings",
            "taj_pick_list_parent_warehouse",
        )

        self.assertTrue(
            value,
            "Pick List parent warehouse is not configured",
        )

    def test_supplier_due_date_override_field_exists(self):
        meta = frappe.get_meta(
            "Supplier"
        )

        self.assertTrue(
            meta.has_field(
                "taj_ignore_due_date_validation"
            )
        )


class TestLiveSchemaIntegration(TestCase):
    def test_production_plan_split_doctype_exists(self):
        self.assertTrue(
            frappe.db.exists(
                "DocType",
                "Production Plan Sub Assembly Split",
            )
        )

    def test_checklist_answer_question_schema(self):
        meta = frappe.get_meta(
            "Checklist Answer Question"
        )

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

        actual = {
            field.fieldname
            for field in meta.fields
        }

        self.assertTrue(
            required.issubset(actual)
        )

    def test_critical_taj_core_doctypes_are_installed(self):
        doctypes = (
            "Supplier Qualification",
            "License",
            "License Type",
            "Raw Material Specification",
            "Maintenance Contract",
            "Product Proposal",
            "Sensory Feedback",
            "Catering Equipment",
            "Catering Equipment Delivery",
            "Catering Equipment Return",
            "Checklist Answer",
        )

        missing = [
            doctype
            for doctype in doctypes
            if not frappe.db.exists(
                "DocType",
                doctype,
            )
        ]

        self.assertEqual(
            [],
            missing,
        )
