# Copyright (c) 2025, Maged BAjandooh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import validate_email_address

class Visitor(Document):
    def validate(self):
        # Validate email format
        try:
            validate_email_address(self.email, True)
        except frappe.ValidationError:
            frappe.throw(_("Invalid email address."))

        # Check duplicate ONLY when creating a NEW document
        if self.is_new():
            existing = frappe.get_all(
                "Visitor",
                filters={"email": self.email, "status": "Open"},
                limit=1
            )
            if existing:
                frappe.throw(_("This visitor already exists."))

            
    def on_submit(self):
        # Ensure only approved/rejected statuses can be submitted
        if self.status not in ["Approved", "Rejected"]:
            frappe.throw(_("Only status 'Approved' and 'Rejected' can be submitted."))

        
        # Send notification email
        self.send_email()

    def send_email(self):
        # Validate email exists before sending
        if not self.email:
            frappe.msgprint("No email address specified. Notification not sent.", alert=True)
            return False

        # Prepare email content based on status
        subject = _("Access to Production Area - TajFF")
        message = _("Dear {name},<br><br>We hope this message finds you well.<br><br>").format(name=self.name1)

        if self.status == 'Approved':
            message += _(
                "We are pleased to inform you that your request for access to the production area has been approved. "
                "Please ensure all safety protocols and guidelines are followed while in the area.<br><br>"
            )
        elif self.status == 'Rejected':
            message += _(
                "After reviewing your request, we regret to inform you that access to the production area "
                "cannot be granted at this time. This decision was made to ensure safety compliance.<br><br>"
            )

        message += _(
            "If you have any questions or require further assistance, please contact us.<br><br>"
            "Best regards,<br>Quality Control Team<br>Taj Food Factory For Ready Meals"
        )

        try:
            # Send email through Frappe's queue system
            frappe.sendmail(
                recipients=[self.email],
                subject=subject,
                message=message,
                reference_doctype=self.doctype,
                reference_name=self.name
            )
            frappe.msgprint(f"Notification email sent to {self.email}", alert=True)
            return True
            
        except Exception as e:
            frappe.log_error(
                title="Email Send Error",
                message=f"Failed to send email for Visitor {self.name}: {str(e)}"
            )
            frappe.msgprint("Error sending email notification. Please check error logs.", alert=True)
            return False
        

def create_new_visitor_notification():
    if not frappe.db.exists("Notification", "New Visitor"):
        notif = frappe.get_doc({
            "doctype": "Notification",
            "name": "New Visitor",
            "document_type": "Visitor",
            "subject": _("New Visitor Registered"),
            "message": "A new visitor has been registered: {{ doc.full_name }} ({{ doc.name }}).<br>"
           "<a href='{{ frappe.utils.get_url() }}/app/visitor/{{ doc.name }}'>Open Visitor</a>",
            "enabled": 1,
            "event": "New",  
            "recipients": []
        })

        # Add roles to Notification Recipients
        notif.append("recipients", {"receiver_by_role": "QC User"})
        notif.append("recipients", {"receiver_by_role": "Quality Manager"})

        notif.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.msgprint(_("Notification 'New Visitor' created successfully."))
    else:
        frappe.msgprint(_("Notification 'New Visitor' already exists."))

