import frappe
from frappe.utils import getdate

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import (
    PurchaseInvoice,
)
from erpnext.accounts.party import validate_due_date


class TajPurchaseInvoice(PurchaseInvoice):
    def validate_due_date(self):
        """
        Preserve normal ERPNext due-date validation.

        For suppliers explicitly configured to ignore the supplier
        invoice-date check, validate against posting_date only instead
        of temporarily clearing bill_date on the document.
        """
        if self.get("is_pos"):
            return

        ignore_bill_date = bool(
            self.supplier
            and frappe.db.get_value(
                "Supplier",
                self.supplier,
                "taj_ignore_due_date_validation",
            )
        )

        if not ignore_bill_date:
            return super().validate_due_date()

        posting_date = self.posting_date

        if (
            frappe.flags.in_import
            and getdate(self.due_date)
            < getdate(posting_date)
        ):
            self.due_date = posting_date
            return

        validate_due_date(
            posting_date,
            self.due_date,
            None,
            self.payment_terms_template,
            self.doctype,
        )
