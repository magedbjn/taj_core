app_name = "taj_core"
app_title = "Taj Core"
app_publisher = "Maged Bajandooh"
app_description = "Core Customizations and common utilities for Taj ERPNext implementation"
app_email = "m.bajandooh@tajff.sa"
app_license = "mit"

doctype_js = {
    "Material Request": "public/js/material_request.js",
    "Purchase Order": "public/js/purchase_order.js",
    "BOM": "public/js/bom.js",
    "Production Plan": "public/js/production_plan.js",
    "Work Order": "public/js/work_order.js",
    "Job Card": "public/js/job_card.js",
}

permission_query_conditions = {
    "Checklist Answer": "taj_core.checklist.permissions.checklist_answer_query_conditions",
}

has_permission = {
    "Checklist Answer": "taj_core.checklist.permissions.checklist_answer_has_permission",
}

scheduler_events = {
	"daily": [
		"taj_core.company_documents.doctype.license.license.scheduled_status_update",
        "taj_core.qc.doctype.supplier_qualification.supplier_qualification.update_certificate_statuses",
        "taj_core.checklist.scheduler.daily_checklist_scheduler",
	],
}

override_doctype_class = {                
    "Party Specific Item": "taj_core.overrides.party_specific_item.TajPartySpecificItem",
    "Leave Application": "taj_core.overrides.leave_application.LeaveApplication",
    "Stock Entry": "taj_core.overrides.stock_entry.CustomStockEntry",
}

override_whitelisted_methods = {
    "hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days":
        "taj_core.overrides.leave_application.get_number_of_leave_days",
    "erpnext.manufacturing.doctype.work_order.work_order.create_pick_list":
		"taj_core.overrides.work_order.create_pick_list",
    "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry":
        "taj_core.overrides.work_order.make_stock_entry"
}

doc_events = {
    "Sensory Feedback": {
        "after_insert": "taj_core.rnd.doctype.sensory_feedback.sensory_feedback.sync_to_product_proposal"
    },
    "Payment Entry": {
        "on_submit": "taj_core.custom.expenses_claim.update_expense_claim_status_on_payment",
        "on_cancel": "taj_core.custom.expenses_claim.revert_expense_claim_status_on_cancel"
    },
    "Journal Entry": {
        "on_submit": "taj_core.custom.expenses_claim.update_expense_claim_status_on_payment",
        "on_cancel": "taj_core.custom.expenses_claim.revert_expense_claim_status_on_cancel",
    },
    "Supplier": {
        "before_insert": "taj_core.integrations.supplier_hooks.ensure_supplier_group_required",
        "validate": "taj_core.integrations.supplier_hooks.validate_supplier_group",
        "after_insert": "taj_core.integrations.supplier_hooks.create_qualification_for_new_supplier",
    },

    "Supplier Qualification Settings": {
        "on_update": "taj_core.integrations.supplier_hooks._clear_qualified_groups_cache",
        "after_insert": "taj_core.integrations.supplier_hooks._clear_qualified_groups_cache",
        "on_trash": "taj_core.integrations.supplier_hooks._clear_qualified_groups_cache",
    },

    "Supplier Qualification": {
        "before_save": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.before_save_capture_status",
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.dedupe_approved_items"
        ],
        "validate": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_approval_status"
        ],
    },

    "Purchase Order": {
        "before_save": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.auto_set_item_status_for_po"
        ],
        "before_submit": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_items_against_qualification",
        ]
    },

    "Purchase Receipt": {
        "before_submit": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_items_against_qualification",
        ]
    },

    "Purchase Invoice": {
        "before_validate": "taj_core.custom.purchase_invoice.before_validate",
        "before_save": "taj_core.custom.purchase_invoice.before_save",
        "before_submit": [
            "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_items_against_qualification",
        ]
    },

    "Request for Quotation": {
        "before_submit": "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_items_against_qualification",
    },

    "Supplier Quotation": {
        "before_submit": "taj_core.qc.doctype.supplier_qualification.supplier_qualification.validate_items_against_qualification",
    },
    "Item":{
        'before_insert': "taj_core.custom.item.update_item_batch_no",
        'before_save': "taj_core.qc.doctype.raw_material_specification.override.item.raw_material_specification"
    },
    "Leave Application": {
        "before_save": "taj_core.overrides.leave_application.before_save_set_total_leave_days",
    },
    # ============================================================
    # Job Card Board Realtime hooks
    # - Publish realtime updates on Job Card changes
    # ============================================================
    "Job Card": {
        "on_update": "taj_core.taj_core.page.job_card_board.job_card_board.job_card_changed",
        "on_trash": "taj_core.taj_core.page.job_card_board.job_card_board.job_card_changed",
        "validate": "taj_core.taj_core.page.job_card_board.job_card_board.job_card_validate_metal_detector_guard"
    },
}



after_install = "taj_core.install.after_install"
before_uninstall = "taj_core.uninstall.before_uninstall"
after_migrate = "taj_core.install.after_migrate"

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["Job Card"]],
            ["fieldname", "like", "taj_%"]
        ]
    }
]
