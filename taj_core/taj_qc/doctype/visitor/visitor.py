# Copyright (c) 2025, Maged BAjandooh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Visitor(Document):
    def validate(self):
        # Check for duplicate visitor entries (same email + date)
        existing_email = frappe.get_all('Visitor', 
            filters={
                'email': self.email, 
                'post_date': self.post_date,
                'name': ('!=', self.name)  # Exclude current document
            },
            limit=1
        )
        if existing_email:
            frappe.throw("This visitor already exists for the selected date!")
            
    def on_submit(self):
        # Ensure only approved/rejected statuses can be submitted
        if self.status not in ["Approved", "Rejected"]:
            frappe.throw("Only status 'Approved' and 'Rejected' can be submitted.")
        
        # Send notification email
        self.send_email()

    def send_email(self):
        # Validate email exists before sending
        if not self.email:
            frappe.msgprint("No email address specified. Notification not sent.", alert=True)
            return False

        # Prepare email content based on status
        subject = "Access to Production Area - Taj Factory"
        message = f"Dear {self.name1},<br><br>We hope this message finds you well.<br><br>"
        
        if self.status == 'Approved':
            message += (
                "We are pleased to inform you that your request for access to the production area has been approved. "
                "Please ensure all safety protocols and guidelines are followed while in the area.<br><br>"
            )
        elif self.status == 'Rejected':
            message += (
                "After reviewing your request, we regret to inform you that access to the production area "
                "cannot be granted at this time. This decision was made to ensure safety compliance.<br><br>"
            )
        
        message += (
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