# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

from pathlib import PurePosixPath

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_IMAGE_SIZE = 2 * 1024 * 1024
HR_ROLES = {"HR User", "HR Manager", "System Manager"}
ASSET_USAGE_OPTIONS = {"Authorized HR Users", "Signatory Only"}



class EmployeeLetterSignatory(Document):
    def validate(self):
        self._set_employee_defaults()
        self._validate_usage_policy()
        self._validate_active_employee()
        self._validate_images()

    def _set_employee_defaults(self):
        if not self.employee:
            return

        employee = frappe.get_doc("Employee", self.employee)
        self.employee_name = employee.employee_name
        self.company = employee.company
        self.designation = employee.designation

        if not self.signatory_name_english:
            self.signatory_name_english = employee.employee_name

        employee_meta = frappe.get_meta("Employee")
        if not self.signatory_name_arabic and employee_meta.has_field("emp_arabic_name"):
            self.signatory_name_arabic = employee.get("emp_arabic_name")

        if not self.title_english:
            self.title_english = employee.designation

    def _validate_usage_policy(self):
        self.signature_usage = self.signature_usage or "Authorized HR Users"
        self.stamp_usage = self.stamp_usage or "Authorized HR Users"

        for fieldname, label in (("signature_usage", _("Signature Usage")), ("stamp_usage", _("Stamp Usage"))):
            if self.get(fieldname) not in ASSET_USAGE_OPTIONS:
                frappe.throw(_("Please select a valid {0}.").format(label))

        if "Signatory Only" not in {self.signature_usage, self.stamp_usage} or not self.employee:
            return

        user_id = frappe.db.get_value("Employee", self.employee, "user_id")
        if not user_id:
            frappe.throw(
                _("Employee {0} must have a User ID before Signature/Stamp Usage can be set to Signatory Only.").format(
                    frappe.bold(self.employee)
                )
            )

    def _validate_active_employee(self):
        if not self.employee or not self.is_active:
            return

        status = frappe.db.get_value("Employee", self.employee, "status")
        if status and status != "Active":
            frappe.throw(
                _("Employee {0} must be Active before the signatory can be enabled.").format(
                    frappe.bold(self.employee)
                )
            )

    def _validate_images(self):
        for fieldname, label in (
            ("signature_image", _("Signature Image")),
            ("stamp_image", _("Stamp Image")),
        ):
            file_url = self.get(fieldname)
            if not file_url:
                continue

            file_row = frappe.db.get_value(
                "File",
                {"file_url": file_url},
                ["name", "file_name", "is_private", "file_size"],
                as_dict=True,
            )
            if not file_row:
                frappe.throw(_("{0} must be uploaded as a Frappe File attachment.").format(frappe.bold(label)))

            suffix = PurePosixPath(file_row.file_name or file_url.split("?", 1)[0]).suffix.lower()
            if suffix not in ALLOWED_IMAGE_EXTENSIONS:
                frappe.throw(_("{0} must be a PNG or JPG image.").format(frappe.bold(label)))
            if not file_row.is_private:
                frappe.throw(_("{0} must be uploaded as a Private file.").format(frappe.bold(label)))
            if file_row.file_size and file_row.file_size > MAX_IMAGE_SIZE:
                frappe.throw(_("{0} must be 2 MB or smaller.").format(frappe.bold(label)))

def _is_asset_usage_allowed(usage, employee_user_id, user, roles):
    usage = usage or "Authorized HR Users"
    if usage == "Signatory Only":
        return bool(employee_user_id and user == employee_user_id)
    return bool(HR_ROLES.intersection(set(roles or [])))


def can_use_signatory_asset(signatory, asset_type, user=None, roles=None):
    """Return whether user may use a stored signature/stamp image.

    `signatory` may be a Document or mapping. This function does not grant DocType
    permission; it only evaluates the asset-usage policy.
    """
    user = user or frappe.session.user
    if roles is None:
        roles = frappe.get_roles(user)

    fieldname = "signature_usage" if asset_type == "signature" else "stamp_usage"
    usage = signatory.get(fieldname) if hasattr(signatory, "get") else getattr(signatory, fieldname, None)
    employee = signatory.get("employee") if hasattr(signatory, "get") else getattr(signatory, "employee", None)
    employee_user_id = frappe.db.get_value("Employee", employee, "user_id") if employee else None
    return _is_asset_usage_allowed(usage, employee_user_id, user, roles)


def validate_signatory_available(signatory_name, company=None):
    """Validate that a signatory record and its linked Employee are currently active."""
    if not signatory_name:
        return None

    signatory = frappe.db.get_value(
        "Employee Letter Signatory",
        signatory_name,
        ["employee", "company", "is_active", "signature_usage", "stamp_usage"],
        as_dict=True,
    )
    if not signatory:
        frappe.throw(_("The selected signatory does not exist."))
    if not signatory.is_active:
        frappe.throw(_("The selected signatory is disabled."))

    employee_status = frappe.db.get_value("Employee", signatory.employee, "status")
    if employee_status != "Active":
        frappe.throw(
            _("The employee linked to signatory {0} is no longer Active. Please select another signatory.").format(
                frappe.bold(signatory.employee)
            )
        )

    if company and signatory.company != company:
        frappe.throw(_("The selected signatory must belong to the same company."))

    return signatory


@frappe.whitelist()
def get_available_signatories(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
    """Link query that hides signatories whose required private assets cannot be used by the current user."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    company = filters.get("company")
    requires_signature = cint(filters.get("requires_signature"))
    requires_stamp = cint(filters.get("requires_stamp"))
    txt = (txt or "").strip().lower()

    rows = frappe.get_all(
        "Employee Letter Signatory",
        filters={"is_active": 1, **({"company": company} if company else {})},
        fields=["name", "employee", "employee_name", "company", "signature_usage", "stamp_usage"],
        order_by="employee_name asc, name asc",
        limit_page_length=500,
    )

    result = []
    for row in rows:
        haystack = " ".join([row.name or "", row.employee or "", row.employee_name or ""]).lower()
        if txt and txt not in haystack:
            continue
        if requires_signature and not can_use_signatory_asset(row, "signature"):
            continue
        if requires_stamp and not can_use_signatory_asset(row, "stamp"):
            continue
        result.append([row.name, row.employee_name or row.employee or row.name])

    start = cint(start)
    page_len = cint(page_len) or 20
    return result[start : start + page_len]


@frappe.whitelist()
def get_asset_access(signatory_name):
    signatory = frappe.get_doc("Employee Letter Signatory", signatory_name)
    return {
        "signature": can_use_signatory_asset(signatory, "signature"),
        "stamp": can_use_signatory_asset(signatory, "stamp"),
        "signature_usage": signatory.signature_usage or "Authorized HR Users",
        "stamp_usage": signatory.stamp_usage or "Authorized HR Users",
    }

def sync_signatory_with_employee_status(doc, method=None):
    """Disable signatory authorization when its linked Employee stops being Active.

    Returning an employee to Active does not re-enable authorization automatically; HR must
    explicitly re-enable the Employee Letter Signatory record.
    """
    if not doc or not getattr(doc, "name", None) or getattr(doc, "status", None) == "Active":
        return

    signatory_name = frappe.db.get_value(
        "Employee Letter Signatory",
        {"employee": doc.name, "is_active": 1},
        "name",
    )
    if signatory_name:
        frappe.db.set_value(
            "Employee Letter Signatory",
            signatory_name,
            "is_active",
            0,
            update_modified=False,
        )
