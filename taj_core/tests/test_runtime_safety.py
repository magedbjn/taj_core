from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe


class TestSupplierQualificationRuntime(TestCase):
    def test_auto_qualification_job_is_queued_outside_parent_transaction(self):
        from taj_core.qc.doctype.supplier_qualification \
            import supplier_qualification as module

        with patch.object(
            module.frappe,
            "enqueue",
            return_value="TEST-JOB",
        ) as enqueue:
            result = module.queue_auto_qualification_request(
                "SUP-TEST"
            )

        self.assertEqual(result, "TEST-JOB")

        enqueue.assert_called_once_with(
            module._AUTO_QUALIFICATION_JOB,
            queue="short",
            job_id=(
                "taj_core:"
                "auto_supplier_qualification:"
                "SUP-TEST"
            ),
            deduplicate=True,
            enqueue_after_commit=False,
            supplier="SUP-TEST",
        )

    def test_queue_error_propagates(self):
        from taj_core.qc.doctype.supplier_qualification \
            import supplier_qualification as module

        with patch.object(
            module.frappe,
            "enqueue",
            side_effect=RuntimeError("queue unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "queue unavailable",
            ):
                module.queue_auto_qualification_request(
                    "SUP-TEST"
                )

    def test_validation_blocks_when_qualification_cannot_be_queued(self):
        from taj_core.integrations \
            import supplier_hooks
        from taj_core.qc.doctype.supplier_qualification \
            import supplier_qualification as module

        purchase_doc = SimpleNamespace(
            supplier="SUP-TEST",
            items=[],
        )

        with patch.object(
            supplier_hooks,
            "is_qualified_supplier_group",
            return_value=True,
        ), patch.object(
            module.frappe.db,
            "get_value",
            return_value="Qualified Group",
        ), patch.object(
            module.frappe,
            "get_all",
            return_value=[],
        ), patch.object(
            module,
            "queue_auto_qualification_request",
            side_effect=RuntimeError("queue failed"),
        ):
            with self.assertRaises(
                frappe.ValidationError
            ):
                module.validate_items_against_qualification(
                    purchase_doc
                )


class TestCertificateSchedulerRuntime(TestCase):
    def test_certificate_scheduler_propagates_database_failure(self):
        from taj_core.qc.doctype.supplier_qualification \
            import supplier_qualification as module

        with patch.object(
            module.frappe.db,
            "sql",
            side_effect=[
                None,
                RuntimeError("certificate update failed"),
            ],
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "certificate update failed",
            ):
                module.update_certificate_statuses()


class TestLicenseSchedulerRuntime(TestCase):
    def test_notification_failure_propagates_from_scheduler(self):
        from taj_core.company_documents.doctype.license \
            import license as module

        rows = [
            {
                "name": "LIC-TEST",
                "license_english": "Test License",
                "status": "Renew",
            }
        ]

        with patch.object(
            module,
            "update_status_bulk",
            return_value=rows,
        ), patch.object(
            module,
            "send_license_notification",
            side_effect=RuntimeError(
                "notification failed"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "notification failed",
            ):
                module.scheduled_status_update()

    def test_active_status_does_not_send_notification(self):
        from taj_core.company_documents.doctype.license \
            import license as module

        rows = [
            {
                "name": "LIC-TEST",
                "license_english": "Test License",
                "status": "Active",
            }
        ]

        with patch.object(
            module,
            "update_status_bulk",
            return_value=rows,
        ), patch.object(
            module,
            "send_license_notification",
        ) as notify:
            module.scheduled_status_update()

        notify.assert_not_called()


class TestVisitorTransactionRuntime(TestCase):
    def test_notification_creation_does_not_commit_manually(self):
        from taj_core.qc.doctype.visitor \
            import visitor as module

        notification = Mock()

        with patch.object(
            module.frappe.db,
            "exists",
            return_value=False,
        ), patch.object(
            module.frappe,
            "get_doc",
            return_value=notification,
        ), patch.object(
            module.frappe,
            "msgprint",
        ), patch.object(
            module.frappe.db,
            "commit",
        ) as commit:
            module.create_new_visitor_notification()

        notification.insert.assert_called_once_with(
            ignore_permissions=True
        )
        commit.assert_not_called()


class TestRMSRuntime(TestCase):
    def test_rms_flag_removed_when_item_save_fails(self):
        from taj_core.qc.doctype \
            .raw_material_specification \
            import raw_material_specification as module

        frappe.flags.pop(
            "in_rms_update",
            None,
        )

        item = SimpleNamespace(
            is_purchase_item=0,
            include_item_in_manufacturing=0,
            save=Mock(
                side_effect=RuntimeError(
                    "item save failed"
                )
            ),
        )

        doc = SimpleNamespace(
            item_code="ITEM-TEST",
            status="Approved",
        )

        with patch.object(
            module.frappe,
            "get_doc",
            return_value=item,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "item save failed",
            ):
                module.RawMaterialSpecification.update_item(
                    doc
                )

        self.assertNotIn(
            "in_rms_update",
            frappe.flags,
        )

    def test_rms_previous_flag_is_restored(self):
        from taj_core.qc.doctype \
            .raw_material_specification \
            import raw_material_specification as module

        previous = "PREVIOUS-VALUE"
        frappe.flags.in_rms_update = previous

        item = SimpleNamespace(
            is_purchase_item=0,
            include_item_in_manufacturing=0,
            save=Mock(),
        )

        doc = SimpleNamespace(
            item_code="ITEM-TEST",
            status="Approved",
        )

        try:
            with patch.object(
                module.frappe,
                "get_doc",
                return_value=item,
            ):
                module.RawMaterialSpecification.update_item(
                    doc
                )

            self.assertEqual(
                frappe.flags.in_rms_update,
                previous,
            )

        finally:
            frappe.flags.pop(
                "in_rms_update",
                None,
            )


class TestPurchaseInvoiceOverrideRuntime(TestCase):
    def _make_doc(self):
        from taj_core.overrides \
            import purchase_invoice as module

        doc = object.__new__(
            module.TajPurchaseInvoice
        )

        doc.__dict__.update(
            {
                "doctype": "Purchase Invoice",
                "is_pos": 0,
                "supplier": "SUP-TEST",
                "posting_date": "2026-09-01",
                "bill_date": "2026-09-10",
                "due_date": "2026-09-05",
                "payment_terms_template": None,
            }
        )

        return module, doc

    def test_supplier_override_preserves_bill_date(self):
        module, doc = self._make_doc()

        marker = object()
        previous = frappe.flags.get(
            "in_import",
            marker,
        )
        frappe.flags.in_import = False

        try:
            with patch.object(
                module.frappe.db,
                "get_value",
                return_value=1,
            ), patch.object(
                module,
                "validate_due_date",
            ) as validator:
                module.TajPurchaseInvoice.validate_due_date(
                    doc
                )

            validator.assert_called_once_with(
                "2026-09-01",
                "2026-09-05",
                None,
                None,
                "Purchase Invoice",
            )

            self.assertEqual(
                doc.bill_date,
                "2026-09-10",
            )

        finally:
            if previous is marker:
                frappe.flags.pop(
                    "in_import",
                    None,
                )
            else:
                frappe.flags.in_import = previous

    def test_import_adjusts_due_date_to_posting_date(self):
        module, doc = self._make_doc()

        doc.due_date = "2026-08-20"

        marker = object()
        previous = frappe.flags.get(
            "in_import",
            marker,
        )
        frappe.flags.in_import = True

        try:
            with patch.object(
                module.frappe.db,
                "get_value",
                return_value=1,
            ), patch.object(
                module,
                "validate_due_date",
            ) as validator:
                module.TajPurchaseInvoice.validate_due_date(
                    doc
                )

            self.assertEqual(
                doc.due_date,
                "2026-09-01",
            )

            validator.assert_not_called()

        finally:
            if previous is marker:
                frappe.flags.pop(
                    "in_import",
                    None,
                )
            else:
                frappe.flags.in_import = previous

    def test_normal_supplier_uses_erpnext_validation(self):
        module, doc = self._make_doc()

        with patch.object(
            module.frappe.db,
            "get_value",
            return_value=0,
        ), patch.object(
            module.PurchaseInvoice,
            "validate_due_date",
        ) as base_validate:
            module.TajPurchaseInvoice.validate_due_date(
                doc
            )

        base_validate.assert_called_once_with()


class TestChecklistAuthorizationRuntime(TestCase):
    def test_non_manager_is_rejected(self):
        from taj_core.checklist \
            import api as module

        with patch.object(
            module,
            "is_checklist_manager",
            return_value=False,
        ):
            with self.assertRaises(
                frappe.PermissionError
            ):
                module._ensure_manager()

    def test_user_cannot_claim_other_users_checklist(self):
        from taj_core.checklist \
            import api as module

        doc = SimpleNamespace(
            docstatus=0,
            status="Open",
            assignment_type="Specific User",
            assigned_user="other@example.com",
            taken_by=None,
        )

        with patch.object(
            module.frappe,
            "get_doc",
            return_value=doc,
        ), patch.object(
            module,
            "is_checklist_manager",
            return_value=False,
        ):
            with self.assertRaises(
                frappe.PermissionError
            ):
                module.claim_checklist_answer(
                    "CHK-TEST"
                )


class TestCateringRuntime(TestCase):
    def test_return_rejects_quantity_above_locked_outstanding(self):
        from taj_core.catering.doctype \
            .catering_equipment_return \
            import catering_equipment_return as module

        delivery_item = SimpleNamespace(
            parent="DEL-TEST",
            outstanding_qty=1,
            equipment="EQ-TEST",
            serial_no=None,
        )

        row = SimpleNamespace(
            idx=1,
            delivery_item="ROW-TEST",
            equipment="EQ-TEST",
            equipment_name_arabic=None,
            return_qty=2,
            has_serial_no=0,
            serial_no=None,
        )

        doc = SimpleNamespace(
            delivery="DEL-TEST",
            items=[row],
            flags=frappe._dict(
                locked_delivery_items={
                    "ROW-TEST": delivery_item
                },
                locked_equipment_units={},
            ),
        )

        with self.assertRaises(
            frappe.ValidationError
        ):
            module.CateringEquipmentReturn \
                .validate_against_current_delivery(
                    doc
                )
