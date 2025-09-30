app_name = "taj_core"
app_title = "Taj Core"
app_publisher = "Maged Bajandooh"
app_description = "Core Customizations and common utilities for Taj ERPNext implementation"
app_email = "m.bajandooh@tajff.sa"
app_license = "mit"


doctype_js = {
    "Material Request": "custom/material_request.js",
    "Production Plan": "public/production_plan/production_plan.js",
}


scheduler_events = {
	"daily": [
		"taj_core.company_documents.doctype.license.license.scheduled_status_update",
	],
    "monthly": [
        "taj_core.public.production_plan.generate_stickers.delete_old_production_stickers"
    ]
}

override_doctype_class = {                
    "Party Specific Item": "taj_core.overrides.party_specific_item.TajPartySpecificItem",
}

doc_events = {
    "Payment Entry": {
        "on_submit": "taj_core.custom.expenses_claim.update_expense_claim_status_on_payment",
        "on_cancel": "taj_core.custom.expenses_claim.revert_expense_claim_status_on_cancel"
    },
    "Journal Entry": {
        "on_submit": "taj_core.custom.expenses_claim.update_expense_claim_status_on_payment",
        "on_cancel": "taj_core.custom.expenses_claim.revert_expense_claim_status_on_cancel",
    },
    "Purchase Invoice": {
        "before_validate": "taj_core.custom.purchase_invoice.before_validate",
        "before_save": "taj_core.custom.purchase_invoice.before_save"
    },
    "Item":{
        'before_save': "taj_core.qc.doctype.raw_material_specification.override.item.raw_material_specification"
    }
}

after_install = "taj_core.install.after_install"

before_uninstall = "taj_core.uninstall.before_uninstall"

# Migrations
# after_migrate = [
#     "taj_core.patches.delete_slnee.execute",
#     "taj_core.patches.delete_custom_fields.execute"
# ]
