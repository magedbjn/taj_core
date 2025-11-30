app_name = "taj_core"
app_title = "Taj Core"
app_publisher = "Maged Bajandooh"
app_description = "Core Customizations and common utilities for Taj ERPNext implementation"
app_email = "m.bajandooh@tajff.sa"
app_license = "mit"

doctype_js = {
    "Production Plan": "public/production_plan/production_plan.js",
    "Material Request": "public/js/material_request.js",
    "Purchase Order": "public/js/purchase_order.js",
    "BOM": "public/js/bom.js",
}


scheduler_events = {
	"daily": [
		"taj_core.company_documents.doctype.license.license.scheduled_status_update",
        "taj_core.qc.doctype.supplier_qualification.supplier_qualification.update_certificate_statuses"
	],
    "monthly": [
        "taj_core.public.production_plan.generate_stickers.delete_old_production_stickers"
    ]
}

override_doctype_class = {                
    "Party Specific Item": "taj_core.overrides.party_specific_item.TajPartySpecificItem",
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
}



after_install = "taj_core.install.after_install"
before_uninstall = "taj_core.uninstall.before_uninstall"
after_migrate = "taj_core.install.after_migrate"

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "in", ["Employee"]],
            ["fieldname", "like", "custom_%"]
        ]
    }
]
