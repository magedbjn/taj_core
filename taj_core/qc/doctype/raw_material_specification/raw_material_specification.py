import frappe
from frappe import _
from frappe.model.document import Document

class RawMaterialSpecification(Document):
    def validate(self):
        self.ensure_unique_item()
        self.update_item()

    def ensure_unique_item(self):
        # إذا كان السجل جديدًا أو تم تغيير item_code
        existing = frappe.db.exists(
            "Raw Material Specification",
            {
                "item_code": self.item_code,
                "name": ["!=", self.name]  # استثناء السجل الحالي أثناء التعديل
            }
        )
        if existing:
            frappe.throw(_("Raw Material Specification already exists for item {0}").format(
                frappe.bold(self.item_code)
            ))

    def update_item(self):
        if not self.item_code:
            frappe.throw(_("Item Code is missing."))

        missing = object()
        previous_flag = frappe.flags.get(
            "in_rms_update",
            missing,
        )

        frappe.flags.in_rms_update = True

        try:
            item = frappe.get_doc(
                "Item",
                self.item_code,
            )

            if self.status == "Approved":
                item.is_purchase_item = 1
                item.include_item_in_manufacturing = 1

            elif self.status == "Rejected":
                item.is_purchase_item = 0
                item.include_item_in_manufacturing = 0
                frappe.msgprint(
                    _(
                        "Item {0} can no longer be purchased "
                        "or used in production."
                    ).format(
                        frappe.bold(self.item_code)
                    ),
                    alert=True,
                )

            else:  # Open / Cancelled
                item.is_purchase_item = 1
                item.include_item_in_manufacturing = 1

            item.save(
                ignore_permissions=True
            )

        finally:
            if previous_flag is missing:
                frappe.flags.pop(
                    "in_rms_update",
                    None,
                )
            else:
                frappe.flags.in_rms_update = (
                    previous_flag
                )
