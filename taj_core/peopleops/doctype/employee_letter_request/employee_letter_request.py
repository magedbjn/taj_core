# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import base64
import json
import mimetypes
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, now, today

from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

from taj_core.peopleops.doctype.employee_letter_signatory.employee_letter_signatory import (
    can_use_signatory_asset,
    validate_signatory_available,
)


HR_ROLES = {"HR User", "HR Manager", "System Manager"}
SALARY_MARKERS = (
    "salary_base",
    "basic_salary",
    "gross_salary",
    "regular_deductions",
    "monthly_salary",
    "net_salary",
    "total_salary",
    "housing_allowance",
    "transport_allowance",
    "telecom_allowance",
    "food_allowance",
    "risk_allowance",
    "salary_currency",
    "salary_components",
    "earnings",
    "deductions",
)


class EmployeeLetterRequest(Document):
    def before_insert(self):
        self.requested_by = frappe.session.user
        self.post_date = self.post_date or today()
        self.as_of_date = self.as_of_date or self.post_date
        self.request_type = self.request_type or "Standard Letter"
        self.language_mode = self.language_mode or "Bilingual"
        self.table_print_style = self.table_print_style or "Standard Borders"
        self._enforce_employee_self_service()
        self._set_employee_snapshot_fields()
        self._apply_request_policy()

    def validate(self):
        self.post_date = self.post_date or today()
        self.as_of_date = self.as_of_date or self.post_date
        self.request_type = self.request_type or "Standard Letter"
        self.language_mode = self.language_mode or "Bilingual"
        self.table_print_style = self.table_print_style or "Standard Borders"
        self._enforce_employee_self_service()
        self._set_employee_snapshot_fields()
        self._apply_request_policy()
        self._validate_request_requirements()
        self._validate_reissue()
        self._validate_duplicate_request()
        self._sync_expiry_flag()

    def before_submit(self):
        self._set_employee_snapshot_fields()
        self._apply_request_policy()
        self._validate_request_requirements(for_issue=True)
        self._validate_duplicate_request()

        self.issue_date = self.issue_date or today()
        self.as_of_date = self.as_of_date or self.issue_date
        self.issued_by = frappe.session.user
        self.issued_on = now()

        if self.has_expiry:
            self.valid_until = add_days(self.issue_date, cint(self.validity_days))
        else:
            self.valid_until = None

        self._prepare_signatory_snapshot()
        self._prepare_salary_snapshot_if_needed()
        self._render_issued_content()
        self._set_employee_snapshot_json()
        self._sync_expiry_flag()

        if self.final_document_method == "Manual Final PDF Upload":
            if not self.final_document_upload:
                frappe.throw(_("Final PDF Upload is required before issuing this letter."))
            self.final_document = self._copy_file_as_private_final(self.final_document_upload)
        else:
            # Dynamic/system-generated letters are printed on demand.
            # Do not retain generated PDFs as attachments.
            self.final_document = None
            self.final_document_upload = None

    def on_submit(self):
        # System-generated letters are rendered on demand through the standard
        # Print action. No PDF/File attachment is created here.
        self._create_fee_additional_salary()

    def on_cancel(self):
        if not self.additional_salary:
            return
        additional = frappe.get_doc("Additional Salary", self.additional_salary)
        if additional.docstatus == 1:
            additional.cancel()
        self.db_set("fee_status", "Pending Payroll Deduction", update_modified=False)

    def onload(self):
        self._sync_expiry_flag()

    def before_print(self, print_settings=None):
        # Draft printing is HR preview only and never creates an attachment.
        if self.docstatus == 0:
            if not _current_user_is_hr():
                frappe.throw(_("Only HR can preview a draft employee letter."), frappe.PermissionError)
            if not self.get("_preview_mode"):
                self._prepare_preview()

        # Arabic-Indic digits are a presentation rule only. Keep the stored
        # snapshot and all source data unchanged, and prepare transient values
        # exclusively for Print / Preview.
        self._prepare_arabic_print_view()

        if self.docstatus == 0:
            return

        self._sync_expiry_flag()
        if not self.is_expired:
            return

        # HR always retains access to the historical record for audit.
        if _current_user_is_hr():
            self._expired_print = 1
            return

        if self.expired_document_policy == "Block Employee Print/Download":
            frappe.throw(
                _("This letter expired on {0}. Please request a new valid letter.").format(self.valid_until),
                frappe.PermissionError,
            )

        # System-generated historical copies are clearly marked expired.
        self._expired_print = 1

    def _prepare_arabic_print_view(self):
        # Presentation-only formatting. Keep the stored snapshot immutable, but
        # normalize salary numbers at print time so previously issued letters
        # also benefit from the current display format.
        salary_snapshot = _parse_salary_snapshot(self.salary_snapshot_json)

        self._print_rendered_subject_english = _format_salary_plain_text(
            self.rendered_subject_english, salary_snapshot
        )
        self._print_rendered_text_english = _format_salary_html_text(
            self.rendered_text_english, salary_snapshot
        )
        self._print_rendered_subject_arabic = _arabicize_plain_text(
            _format_salary_plain_text(self.rendered_subject_arabic, salary_snapshot)
        )
        self._print_rendered_text_arabic = _arabicize_html_text(
            _format_salary_html_text(self.rendered_text_arabic, salary_snapshot)
        )

        print_sections = []
        for row in self.rendered_sections or []:
            data = frappe._dict(row.as_dict())
            data.section_title_english = _format_salary_plain_text(
                row.section_title_english, salary_snapshot
            )
            data.content_english = _format_salary_html_text(
                row.content_english, salary_snapshot
            )
            data.section_title_arabic = _arabicize_plain_text(
                _format_salary_plain_text(row.section_title_arabic, salary_snapshot)
            )
            data.content_arabic = _arabicize_html_text(
                _format_salary_html_text(row.content_arabic, salary_snapshot)
            )
            print_sections.append(data)
        self._print_rendered_sections = print_sections

    def _enforce_employee_self_service(self):
        if _current_user_is_hr():
            return

        if "Employee" not in frappe.get_roles(frappe.session.user):
            return

        employee = _employee_for_user(frappe.session.user)
        if not employee:
            frappe.throw(_("No active Employee record is linked to your user account."))

        if self.employee and self.employee != employee:
            frappe.throw(_("Employees can create letter requests only for themselves."))

        self.employee = employee
        self.post_date = today()
        self.as_of_date = self.post_date
        self.reissue_of = None
        self.reissue_reason = None

    def _set_employee_snapshot_fields(self):
        if not self.employee:
            return

        employee = frappe.get_doc("Employee", self.employee)
        self.employee_name = employee.employee_name
        self.company = employee.company
        self.department = employee.department
        self.designation = employee.designation
        self.date_of_joining = employee.date_of_joining

        employee_meta = frappe.get_meta("Employee")
        if employee_meta.has_field("emp_arabic_name"):
            self.employee_name_arabic = employee.get("emp_arabic_name")

    def _get_effective_template(self):
        template_name = None
        if self.request_type == "Standard Letter":
            template_name = self.letter_template
        elif self.request_type == "Custom Letter" and self.resolution_mode == "Existing Template":
            template_name = self.resolved_template

        if not template_name:
            return None
        return frappe.get_doc("Employee Document Template", template_name)

    def _apply_request_policy(self):
        if self.request_type == "Standard Letter":
            if not self.letter_template:
                return
            self._apply_template_policy(frappe.get_doc("Employee Document Template", self.letter_template))
            return

        if self.request_type != "Custom Letter":
            return

        if self.resolution_mode == "Existing Template" and self.resolved_template:
            template = frappe.get_doc("Employee Document Template", self.resolved_template)
            if self.language_mode and template.language_mode != self.language_mode:
                frappe.throw(_("Resolved Template language must match the language requested by the employee."))
            self._apply_template_policy(template)
            return

        if self.resolution_mode == "One-Time Letter":
            self.requires_approval = 1
            self.requires_purpose = 1
            self.requires_addressed_to = 1
            self.requires_signature = cint(self.one_time_requires_signature)
            self.requires_stamp = cint(self.one_time_requires_stamp)
            self.final_document_method = self.one_time_final_document_method or "System Generated PDF"
            self.table_print_style = "Standard Borders"
            self.has_expiry = cint(self.one_time_has_expiry)
            self.validity_days = cint(self.one_time_validity_days) if self.has_expiry else 0
            self.expired_document_policy = (
                self.one_time_expired_document_policy or "Historical Copy with EXPIRED Watermark"
            ) if self.has_expiry else None
            if self.has_expiry and self.final_document_method == "Manual Final PDF Upload":
                self.expired_document_policy = "Block Employee Print/Download"
            self.letter_head = self._company_default_letter_head()
            self.signatory = self.one_time_signatory if (self.requires_signature or self.requires_stamp) else None
            self.fee_policy = self.one_time_fee_policy or "No Fee"
            self.fee_amount = flt(self.one_time_fee_amount) if self.fee_policy != "No Fee" else 0
            self.employee_fee_salary_component = self.one_time_fee_salary_component if self.fee_policy == "Employee Pays" else None
            self._set_fee_status()
            return

        # A custom request may be saved by an employee before HR resolves it.
        self.requires_approval = 1
        self.requires_purpose = 1
        self.requires_addressed_to = 1
        self.requires_signature = 0
        self.requires_stamp = 0
        self.has_expiry = 0
        self.validity_days = 0
        self.expired_document_policy = None
        self.final_document_method = "System Generated PDF"
        self.table_print_style = "Standard Borders"
        self.letter_head = self._company_default_letter_head()
        self.fee_policy = "No Fee"
        self.fee_amount = 0
        self.employee_fee_salary_component = None
        self._set_fee_status()

    def _apply_template_policy(self, template):
        if not template.is_active:
            frappe.throw(_("The selected letter template is disabled."))
        if not template.available_for_employee_request and not _current_user_is_hr():
            frappe.throw(_("The selected letter template is not available for employee requests."))
        if self.company and template.company != self.company:
            frappe.throw(_("The letter template must belong to the employee company."))

        self.language_mode = template.language_mode
        self.bilingual_layout = template.bilingual_layout if template.language_mode == "Bilingual" else None
        self.requires_approval = template.requires_approval
        self.requires_purpose = template.requires_purpose
        self.requires_addressed_to = template.requires_addressed_to
        self.requires_signature = template.requires_signature
        self.requires_stamp = template.requires_stamp
        self.final_document_method = template.final_document_method
        self.table_print_style = template.table_print_style or "Standard Borders"
        self.has_expiry = template.has_expiry
        self.validity_days = template.validity_days if template.has_expiry else 0
        self.expired_document_policy = template.expired_document_policy if template.has_expiry else None
        if self.has_expiry and self.final_document_method == "Manual Final PDF Upload":
            self.expired_document_policy = "Block Employee Print/Download"
        self.letter_head = template.letter_head

        if not self.signatory:
            self.signatory = template.default_signatory

        self.fee_policy = template.fee_policy
        self.fee_amount = template.fee_amount
        self.employee_fee_salary_component = template.employee_fee_salary_component
        self._set_fee_status()

    def _set_fee_status(self):
        if self.fee_policy == "Employee Pays":
            if self.waive_fee:
                if not _current_user_is_hr():
                    frappe.throw(_("Only HR can waive an employee letter fee."))
                if not (self.fee_waiver_reason or "").strip():
                    frappe.throw(_("Fee Waiver Reason is required."))
                self.fee_status = "Waived"
            elif self.fee_status != "Charged":
                self.fee_status = "Pending Payroll Deduction"
        elif self.fee_policy == "Company Pays":
            self.waive_fee = 0
            self.fee_waiver_reason = None
            self.fee_status = "Company Paid"
        else:
            self.waive_fee = 0
            self.fee_waiver_reason = None
            self.fee_status = "Not Applicable"

    def _company_currency(self):
        return frappe.db.get_value("Company", self.company, "default_currency") if self.company else None

    def _company_default_letter_head(self):
        return frappe.db.get_value("Company", self.company, "default_letter_head") if self.company else None

    def _validate_request_requirements(self, for_issue=False):
        if not self.employee:
            frappe.throw(_("Employee is required."))

        if self.request_type == "Standard Letter":
            if not self.letter_template:
                frappe.throw(_("Letter Template is required for a standard request."))
        elif self.request_type == "Custom Letter":
            if self.language_mode in {"English Only", "Bilingual"} and not (self.custom_letter_title_english or "").strip():
                frappe.throw(_("Requested Letter Title (English) is required."))
            if self.language_mode in {"Arabic Only", "Bilingual"} and not (self.custom_letter_title_arabic or "").strip():
                frappe.throw(_("Requested Letter Title (Arabic) is required."))
            if not (self.request_details or "").strip():
                frappe.throw(_("Request Details are required for a custom letter."))
            if for_issue:
                if self.resolution_mode not in {"Existing Template", "One-Time Letter"}:
                    frappe.throw(_("HR must resolve the custom request before it can be issued."))
                if self.resolution_mode == "Existing Template" and not self.resolved_template:
                    frappe.throw(_("Resolved Template is required."))
                if self.resolution_mode == "One-Time Letter":
                    self._validate_one_time_content()
        else:
            frappe.throw(_("Please select a valid Request Type."))

        if self.requires_purpose and not (self.purpose or "").strip():
            frappe.throw(_("Purpose is required for this letter type."))

        if self.requires_addressed_to or self.request_type == "Custom Letter":
            if self.language_mode in {"English Only", "Bilingual"} and not (self.addressed_to or "").strip():
                frappe.throw(_("Addressed To (English) is required for this letter type."))
            if self.language_mode in {"Arabic Only", "Bilingual"} and not (self.addressed_to_arabic or "").strip():
                frappe.throw(_("Addressed To (Arabic) is required for this letter type."))

        if self.required_by and self.post_date and getdate(self.required_by) < getdate(self.post_date):
            frappe.throw(_("Required By cannot be before the Request Date."))

    def _validate_one_time_content(self):
        if self.language_mode in {"English Only", "Bilingual"} and not _has_content(self.one_time_text_english):
            frappe.throw(_("One-Time Content (English) is required."))
        if self.language_mode in {"Arabic Only", "Bilingual"} and not _has_content(self.one_time_text_arabic):
            frappe.throw(_("One-Time Content (Arabic) is required."))
        if self.one_time_has_expiry and cint(self.one_time_validity_days) <= 0:
            frappe.throw(_("One-Time Validity (Days) must be greater than zero."))
        if self.one_time_has_expiry:
            allowed = {
                "Historical Copy with EXPIRED Watermark",
                "Block Employee Print/Download",
            }
            if self.one_time_expired_document_policy not in allowed:
                self.one_time_expired_document_policy = "Historical Copy with EXPIRED Watermark"
            if self.one_time_final_document_method == "Manual Final PDF Upload":
                self.one_time_expired_document_policy = "Block Employee Print/Download"
        if self.one_time_fee_policy != "No Fee" and flt(self.one_time_fee_amount) <= 0:
            frappe.throw(_("One-Time Fee Amount must be greater than zero."))
        if self.one_time_fee_policy == "Employee Pays" and self.one_time_fee_salary_component:
            component = frappe.db.get_value(
                "Salary Component", self.one_time_fee_salary_component, ["type", "disabled"], as_dict=True
            )
            if not component or component.type != "Deduction" or component.disabled:
                frappe.throw(_("One-Time Fee Salary Component must be an enabled Deduction component."))

    def _validate_reissue(self):
        if not self.reissue_of:
            return
        if not _current_user_is_hr():
            frappe.throw(_("Only HR can authorize a reissue while a previous letter is still valid."))
        if not (self.reissue_reason or "").strip():
            frappe.throw(_("Reissue Reason is required."))

        original = frappe.db.get_value(
            "Employee Letter Request",
            self.reissue_of,
            ["employee", "request_type", "letter_template"],
            as_dict=True,
        )
        if not original:
            frappe.throw(_("The original letter request does not exist."))
        if original.employee != self.employee:
            frappe.throw(_("Reissue Of must belong to the same employee."))
        if original.request_type != self.request_type:
            frappe.throw(_("Reissue Of must use the same request type."))
        if self.request_type == "Standard Letter" and original.letter_template != self.letter_template:
            frappe.throw(_("Reissue Of must use the same letter template."))

    def _validate_duplicate_request(self):
        if self.reissue_of or not self.employee:
            return

        template = self._get_effective_template()
        if self.request_type == "Standard Letter" and template and not template.prevent_duplicate_while_valid:
            prevent_issued_duplicate = False
        else:
            prevent_issued_duplicate = True

        rows = frappe.get_all(
            "Employee Letter Request",
            filters={"employee": self.employee, "docstatus": ["!=", 2]},
            fields=[
                "name", "docstatus", "request_type", "letter_template", "resolved_template",
                "custom_letter_title_english", "custom_letter_title_arabic", "language_mode",
                "addressed_to", "addressed_to_arabic", "valid_until", "has_expiry", "is_expired",
            ],
            order_by="creation desc",
        )

        for row in rows:
            if row.name == self.name or not self._same_request_identity(row, template):
                continue
            if row.docstatus == 0:
                frappe.throw(
                    _("A matching letter request already exists: {0}.").format(frappe.bold(row.name))
                )
            if not prevent_issued_duplicate:
                continue
            still_valid = not cint(row.is_expired) and (not row.has_expiry or not row.valid_until or getdate(row.valid_until) >= getdate(today()))
            if still_valid:
                valid_text = _(" without an expiry date") if not row.has_expiry else _(" until {0}").format(row.valid_until)
                frappe.throw(
                    _("You already have the same issued letter {0}, valid{1}. Please use the existing PDF or ask HR for an authorized reissue.").format(
                        frappe.bold(row.name), valid_text
                    )
                )

    def _same_request_identity(self, row, template=None):
        if row.request_type != self.request_type:
            return False
        if (row.language_mode or "") != (self.language_mode or ""):
            return False

        if self.request_type == "Standard Letter":
            if row.letter_template != self.letter_template:
                return False
            scope = (template.duplicate_match_scope if template else None) or "Same Template and Recipient"
            if scope == "Same Template":
                return True
        else:
            if _normalize_identity_text(row.custom_letter_title_english) != _normalize_identity_text(self.custom_letter_title_english):
                return False
            if _normalize_identity_text(row.custom_letter_title_arabic) != _normalize_identity_text(self.custom_letter_title_arabic):
                return False

        return (
            _normalize_identity_text(row.addressed_to) == _normalize_identity_text(self.addressed_to)
            and _normalize_identity_text(row.addressed_to_arabic) == _normalize_identity_text(self.addressed_to_arabic)
        )

    def _prepare_signatory_snapshot(self, for_preview=False):
        if not (self.requires_signature or self.requires_stamp):
            self.signatory = None
            self.signatory_name_english = None
            self.signatory_name_arabic = None
            self.signatory_title_english = None
            self.signatory_title_arabic = None
            self.signature_image_data = None
            self.stamp_image_data = None
            return

        if not self.signatory:
            if for_preview:
                self.signatory_name_english = None
                self.signatory_name_arabic = None
                self.signatory_title_english = None
                self.signatory_title_arabic = None
                self.signature_image_data = None
                self.stamp_image_data = None
                return
            frappe.throw(_("Please select an Authorized Signatory before issuing the letter."))

        validate_signatory_available(self.signatory, company=self.company)
        signatory = frappe.get_doc("Employee Letter Signatory", self.signatory)

        self.signatory_name_english = signatory.signatory_name_english
        self.signatory_name_arabic = signatory.signatory_name_arabic
        self.signatory_title_english = signatory.title_english
        self.signatory_title_arabic = signatory.title_arabic

        if self.requires_signature:
            signature_allowed = can_use_signatory_asset(signatory, "signature", user=frappe.session.user)
            if not signature_allowed:
                self.signature_image_data = None
                if not for_preview:
                    frappe.throw(
                        _("The selected signature is Signatory Only. {0} must issue/approve this letter using the User ID linked to that Employee.").format(
                            frappe.bold(signatory.employee_name or signatory.employee)
                        ),
                        frappe.PermissionError,
                    )
            elif signatory.signature_image:
                self.signature_image_data = _file_url_to_data_uri(signatory.signature_image)
            elif self.final_document_method == "System Generated PDF" and not for_preview:
                frappe.throw(_("The selected signatory does not have a Signature Image."))
            else:
                self.signature_image_data = None
        else:
            self.signature_image_data = None

        if self.requires_stamp:
            stamp_allowed = can_use_signatory_asset(signatory, "stamp", user=frappe.session.user)
            if not stamp_allowed:
                self.stamp_image_data = None
                if not for_preview:
                    frappe.throw(
                        _("The selected stamp is Signatory Only. {0} must issue/approve this letter using the User ID linked to that Employee.").format(
                            frappe.bold(signatory.employee_name or signatory.employee)
                        ),
                        frappe.PermissionError,
                    )
            elif signatory.stamp_image:
                self.stamp_image_data = _file_url_to_data_uri(signatory.stamp_image)
            elif self.final_document_method == "System Generated PDF" and not for_preview:
                frappe.throw(_("The selected signatory does not have a Stamp Image."))
            else:
                self.stamp_image_data = None
        else:
            self.stamp_image_data = None

    def _template_source_values(self):
        template = self._get_effective_template()
        if template:
            values = [template.letter_subject_english, template.letter_subject_arabic]
            if (template.content_mode or "Single Content") == "Sections":
                for row in template.sections:
                    values.extend([row.section_title_english, row.section_title_arabic, row.content_english, row.content_arabic])
            else:
                values.extend([template.template_text_english, template.template_text_arabic])
            return values
        if self.request_type == "Custom Letter" and self.resolution_mode == "One-Time Letter":
            return [self.one_time_subject_english, self.one_time_subject_arabic, self.one_time_text_english, self.one_time_text_arabic]
        return []

    def _prepare_salary_snapshot_if_needed(self):
        template_text = "\n".join(filter(None, self._template_source_values()))
        if not _template_needs_salary(template_text):
            self._clear_salary_snapshot()
            return

        salary = _get_regular_salary_snapshot(
            employee=self.employee,
            as_of_date=self.as_of_date or self.issue_date or self.post_date,
        )

        self.salary_structure = salary.get("salary_structure")
        self.salary_structure_assignment = salary.get("salary_structure_assignment")
        self.salary_currency = salary.get("salary_currency")
        self.salary_base = salary.get("salary_base")
        self.basic_salary = salary.get("basic_salary")
        self.gross_salary = salary.get("gross_salary")
        self.regular_deductions = salary.get("regular_deductions")
        self.monthly_salary = salary.get("monthly_salary")
        self.salary_snapshot_json = json.dumps(salary, ensure_ascii=False, default=str, indent=2)

    def _clear_salary_snapshot(self):
        for fieldname in (
            "salary_structure", "salary_structure_assignment", "salary_currency", "salary_base",
            "basic_salary", "gross_salary", "regular_deductions", "monthly_salary", "salary_snapshot_json",
        ):
            self.set(fieldname, None)

    def _render_issued_content(self):
        context = self._build_render_context()
        template = self._get_effective_template()
        self.set("rendered_sections", [])

        if template:
            self.rendered_subject_english = _render(template.letter_subject_english, context)
            self.rendered_subject_arabic = _render(template.letter_subject_arabic, context)
            if (template.content_mode or "Single Content") == "Sections":
                self.rendered_text_english = None
                self.rendered_text_arabic = None
                for row in template.sections:
                    self.append(
                        "rendered_sections",
                        {
                            "section_title_english": _render(row.section_title_english, context),
                            "section_title_arabic": _render(row.section_title_arabic, context),
                            "page_break_before": row.page_break_before,
                            "keep_together": row.keep_together,
                            "content_english": _render(row.content_english, context),
                            "content_arabic": _render(row.content_arabic, context),
                        },
                    )
            else:
                self.rendered_text_english = _render(template.template_text_english, context)
                self.rendered_text_arabic = _render(template.template_text_arabic, context)
            return

        self.rendered_subject_english = _render(self.one_time_subject_english, context)
        self.rendered_subject_arabic = _render(self.one_time_subject_arabic, context)
        self.rendered_text_english = _render(self.one_time_text_english, context)
        self.rendered_text_arabic = _render(self.one_time_text_arabic, context)

    def _build_render_context(self):
        employee = frappe.get_cached_doc("Employee", self.employee)
        company = frappe.get_cached_doc("Company", self.company)
        employee_meta = frappe.get_meta("Employee")
        company_meta = frappe.get_meta("Company")

        salary_snapshot = {}
        if self.salary_snapshot_json:
            try:
                salary_snapshot = json.loads(self.salary_snapshot_json)
            except Exception:
                salary_snapshot = {}

        company_name_arabic = ""
        for fieldname in ("arabic_name", "company_name_in_arabic"):
            if company_meta.has_field(fieldname) and company.get(fieldname):
                company_name_arabic = company.get(fieldname)
                break

        return {
            "employee": self.employee,
            "employee_name": self.employee_name or employee.employee_name,
            "employee_name_arabic": self.employee_name_arabic or "",
            "first_name": employee.first_name or "",
            "middle_name": employee.middle_name or "",
            "last_name": employee.last_name or "",
            "employee_number": employee.employee_number or "",
            "designation": self.designation or employee.designation or "",
            "job_title": self.designation or employee.designation or "",
            "department": self.department or employee.department or "",
            "branch": employee.branch or "",
            "grade": employee.grade or "",
            "employment_type": employee.employment_type or "",
            "gender": employee.gender or "",
            "date_of_birth": employee.date_of_birth or "",
            "date_of_joining": self.date_of_joining or employee.date_of_joining or "",
            "relieving_date": employee.relieving_date or "",
            "works_since": self.date_of_joining or employee.date_of_joining or "",
            "nationality": employee.get("taj_nationality") if employee_meta.has_field("taj_nationality") else "",
            "id_number": employee.get("taj_id_number") if employee_meta.has_field("taj_id_number") else "",
            "passport_number": employee.passport_number or "",
            "passport_valid_until": employee.valid_upto or "",
            "short_address": employee.get("taj_short_address") if employee_meta.has_field("taj_short_address") else "",
            "bank_name": employee.bank_name or "",
            "iban": employee.get("iban") if employee_meta.has_field("iban") else "",
            "company_name": company.company_name or self.company,
            "company_name_arabic": company_name_arabic,
            "company_cr_number": company.get("cr_number") if company_meta.has_field("cr_number") else "",
            "company_tax_id": company.tax_id or "",
            "company_country": company.country or "",
            "addressed_to": self.addressed_to or "",
            "addressed_to_arabic": self.addressed_to_arabic or "",
            "purpose": self.purpose or "",
            "request_date": self.post_date or "",
            "issue_date": self.issue_date or "",
            "valid_until": self.valid_until or "",
            "required_by": self.required_by or "",
            "salary_base": _format_print_number(salary_snapshot.get("salary_base")),
            "basic_salary": _format_print_number(salary_snapshot.get("basic_salary")),
            "gross_salary": _format_print_number(salary_snapshot.get("gross_salary")),
            "regular_deductions": _format_print_number(salary_snapshot.get("regular_deductions")),
            "monthly_salary": _format_print_number(salary_snapshot.get("monthly_salary")),
            "net_salary": _format_print_number(salary_snapshot.get("monthly_salary")),
            "total_salary": _format_print_number(salary_snapshot.get("gross_salary")),
            "housing_allowance": _format_print_number(salary_snapshot.get("housing_allowance")),
            "transport_allowance": _format_print_number(salary_snapshot.get("transport_allowance")),
            "telecom_allowance": _format_print_number(salary_snapshot.get("telecom_allowance")),
            "food_allowance": _format_print_number(salary_snapshot.get("food_allowance")),
            "risk_allowance": _format_print_number(salary_snapshot.get("risk_allowance")),
            "salary_currency": salary_snapshot.get("salary_currency") or self.salary_currency or "",
            "salary_components": salary_snapshot.get("salary_components") or {},
            "earnings": salary_snapshot.get("earnings") or {},
            "deductions": salary_snapshot.get("deductions") or {},
            "signatory_name_english": self.signatory_name_english or "",
            "signatory_name_arabic": self.signatory_name_arabic or "",
            "signatory_title_english": self.signatory_title_english or "",
            "signatory_title_arabic": self.signatory_title_arabic or "",
        }

    def _set_employee_snapshot_json(self):
        employee = frappe.get_cached_doc("Employee", self.employee)
        employee_meta = frappe.get_meta("Employee")
        snapshot = {
            "employee": self.employee,
            "employee_name": self.employee_name,
            "employee_name_arabic": self.employee_name_arabic,
            "first_name": employee.first_name,
            "middle_name": employee.middle_name,
            "last_name": employee.last_name,
            "employee_number": employee.employee_number,
            "company": self.company,
            "department": self.department,
            "designation": self.designation,
            "branch": employee.branch,
            "grade": employee.grade,
            "employment_type": employee.employment_type,
            "gender": employee.gender,
            "date_of_birth": employee.date_of_birth,
            "date_of_joining": self.date_of_joining,
            "relieving_date": employee.relieving_date,
            "nationality": employee.get("taj_nationality") if employee_meta.has_field("taj_nationality") else None,
            "id_number": employee.get("taj_id_number") if employee_meta.has_field("taj_id_number") else None,
            "passport_number": employee.passport_number,
            "passport_valid_until": employee.valid_upto,
            "short_address": employee.get("taj_short_address") if employee_meta.has_field("taj_short_address") else None,
            "bank_name": employee.bank_name,
            "iban": employee.get("iban") if employee_meta.has_field("iban") else None,
            "as_of_date": self.as_of_date,
        }
        self.employee_snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str, indent=2)

    def _sync_expiry_flag(self):
        self.is_expired = cint(bool(self.valid_until and getdate(today()) > getdate(self.valid_until)))

    def _create_fee_additional_salary(self):
        if self.fee_policy != "Employee Pays" or flt(self.fee_amount) <= 0:
            return
        if self.fee_status == "Waived":
            return
        if self.additional_salary:
            existing_status = frappe.db.get_value("Additional Salary", self.additional_salary, "docstatus")
            if existing_status == 1:
                self.db_set("fee_status", "Charged", update_modified=False)
                return
        if not self.employee_fee_salary_component:
            # The fee policy is active, but payroll posting is intentionally deferred until HR
            # configures a real Deduction Salary Component with the correct accounting setup.
            return

        component = frappe.db.get_value(
            "Salary Component", self.employee_fee_salary_component, ["type", "disabled"], as_dict=True
        )
        if not component or component.type != "Deduction" or component.disabled:
            frappe.throw(_("Employee Fee Salary Component must be an enabled Deduction component."))

        duplicate = frappe.db.get_value(
            "Additional Salary",
            {"ref_doctype": self.doctype, "ref_docname": self.name, "docstatus": ["!=", 2]},
            "name",
        )
        if duplicate:
            self.db_set("additional_salary", duplicate, update_modified=False)
            self.db_set("fee_status", "Charged", update_modified=False)
            return

        additional = frappe.new_doc("Additional Salary")
        additional.employee = self.employee
        additional.company = self.company
        additional.salary_component = self.employee_fee_salary_component
        additional.type = "Deduction"
        additional.currency = self._company_currency()
        additional.amount = flt(self.fee_amount)
        additional.payroll_date = self.issue_date or today()
        additional.is_recurring = 0
        additional.overwrite_salary_structure_amount = 0
        additional.ref_doctype = self.doctype
        additional.ref_docname = self.name
        additional.insert(ignore_permissions=True)
        additional.submit()

        self.db_set("additional_salary", additional.name, update_modified=False)
        self.db_set("fee_status", "Charged", update_modified=False)

    def _prepare_preview(self):
        self._set_employee_snapshot_fields()
        self._apply_request_policy()
        self._validate_request_requirements(for_issue=True)
        self.issue_date = today()
        self.as_of_date = self.as_of_date or self.issue_date
        self.valid_until = add_days(self.issue_date, cint(self.validity_days)) if self.has_expiry else None
        self._prepare_signatory_snapshot(for_preview=True)
        self._prepare_salary_snapshot_if_needed()
        self._render_issued_content()
        self._set_employee_snapshot_json()
        self._sync_expiry_flag()
        self._preview_mode = 1

    def _copy_file_as_private_final(self, file_url):
        source = frappe.db.get_value(
            "File", {"file_url": file_url}, ["name", "file_name"], as_dict=True,
        )
        if not source:
            frappe.throw(_("The uploaded final document could not be found."))

        source_doc = frappe.get_doc("File", source.name)
        content = source_doc.get_content()
        file_name = source.file_name or f"{self.name}.pdf"
        if not file_name.lower().endswith(".pdf"):
            frappe.throw(_("Final PDF Upload must be a PDF file."))

        file_doc = frappe.get_doc(
            {
                "doctype": "File", "file_name": file_name, "content": content, "is_private": 1,
                "attached_to_doctype": self.doctype, "attached_to_name": self.name,
                "attached_to_field": "final_document",
            }
        ).insert(ignore_permissions=True)

        if (
            source_doc.attached_to_doctype == self.doctype
            and source_doc.attached_to_name == self.name
            and source_doc.attached_to_field == "final_document_upload"
        ):
            frappe.delete_doc("File", source_doc.name, ignore_permissions=True)
            self.final_document_upload = None

        return file_doc.file_url


@frappe.whitelist()
def get_draft_preview(name):
    if not _current_user_is_hr():
        frappe.throw(_("Only HR can preview a draft employee letter."), frappe.PermissionError)

    doc = frappe.get_doc("Employee Letter Request", name)
    if doc.docstatus != 0:
        frappe.throw(_("Draft preview is available only before issue."))
    if not doc.has_permission("write"):
        frappe.throw(_("You do not have permission to process this request."), frappe.PermissionError)

    doc._prepare_preview()

    # Render through the same Print Format used after issue, but do not create
    # a File/PDF attachment and do not update the database.
    original_docstatus = doc.docstatus
    doc.docstatus = 1
    try:
        html = frappe.get_print(
            doc.doctype,
            doc.name,
            "Employee Letter Request",
            doc=doc,
            as_pdf=False,
            letterhead=doc.letter_head or None,
            no_letterhead=0,
        )
    finally:
        doc.docstatus = original_docstatus

    return {"html": html}


_ARABIC_DIGIT_TRANSLATION = str.maketrans({
    "0": "٠", "1": "١", "2": "٢", "3": "٣", "4": "٤",
    "5": "٥", "6": "٦", "7": "٧", "8": "٨", "9": "٩",
})
_HTML_PRINT_TOKEN_RE = re.compile(
    r"(<[^>]+>|&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)"
)


def _format_print_number(value):
    if value in (None, ""):
        return ""

    number = flt(value)
    text = f"{number:,.2f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _parse_salary_snapshot(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) or {}
    except Exception:
        return {}


def _salary_print_values(salary_snapshot):
    values = []
    for fieldname in (
        "salary_base",
        "basic_salary",
        "gross_salary",
        "regular_deductions",
        "monthly_salary",
        "housing_allowance",
        "transport_allowance",
        "telecom_allowance",
        "food_allowance",
        "risk_allowance",
    ):
        raw = salary_snapshot.get(fieldname)
        if raw in (None, ""):
            continue
        try:
            number = flt(raw)
        except Exception:
            continue
        formatted = _format_print_number(number)
        candidates = {str(raw), str(number), f"{number:g}", f"{number:.1f}", f"{number:.2f}"}
        # Do not replace an already formatted value. Longest candidates first
        # prevent matching the integer part of a decimal representation.
        for candidate in sorted(candidates, key=len, reverse=True):
            if candidate and candidate != formatted:
                values.append((candidate, formatted))
    return values


def _format_salary_plain_text(value, salary_snapshot):
    if value in (None, ""):
        return value
    text = str(value)
    for candidate, formatted in _salary_print_values(salary_snapshot):
        pattern = rf"(?<![\d.,]){re.escape(candidate)}(?![\d.,])"
        text = re.sub(pattern, formatted, text)
    return text


def _format_salary_html_text(value, salary_snapshot):
    if value in (None, ""):
        return value
    parts = _HTML_PRINT_TOKEN_RE.split(str(value))
    return "".join(
        part
        if (part.startswith("<") or (part.startswith("&") and part.endswith(";")))
        else _format_salary_plain_text(part, salary_snapshot)
        for part in parts
    )


def _arabicize_plain_text(value):
    if value in (None, ""):
        return value

    # Keep Western punctuation for financial readability in both languages:
    # 9,315.0 -> ٩,٣١٥.٠. Only the digits themselves are localized.
    return str(value).translate(_ARABIC_DIGIT_TRANSLATION)


def _arabicize_html_text(value):
    if value in (None, ""):
        return value

    # Preserve HTML tags, CSS attributes and entities. Only visible text nodes
    # receive Arabic-Indic digits, so e.g. font-size:14px remains valid CSS.
    parts = _HTML_PRINT_TOKEN_RE.split(str(value))
    return "".join(
        part
        if (part.startswith("<") or (part.startswith("&") and part.endswith(";")))
        else _arabicize_plain_text(part)
        for part in parts
    )


def _render(value, context):
    return frappe.render_template(value, context) if value else None


def _has_content(value):
    if not value:
        return False
    return bool(frappe.utils.strip_html(value or "").replace("&nbsp;", " ").strip())


def _normalize_identity_text(value):
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def update_expired_employee_letters():
    current_date = getdate(today())
    rows = frappe.get_all(
        "Employee Letter Request",
        filters={"docstatus": 1},
        fields=["name", "valid_until", "is_expired"],
    )
    for row in rows:
        expired = cint(bool(row.valid_until and current_date > getdate(row.valid_until)))
        if cint(row.is_expired) != expired:
            frappe.db.set_value(
                "Employee Letter Request",
                row.name,
                "is_expired",
                expired,
                update_modified=False,
            )


def _employee_for_user(user):
    return frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        "name",
    )


def _current_user_is_hr():
    return bool(HR_ROLES.intersection(frappe.get_roles(frappe.session.user)))


def _template_needs_salary(template_text):
    text = template_text or ""
    return any(marker in text for marker in SALARY_MARKERS)


def _get_regular_salary_snapshot(employee, as_of_date):
    assignment = frappe.get_all(
        "Salary Structure Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "from_date": ["<=", getdate(as_of_date)],
        },
        fields=["name", "salary_structure", "base", "variable", "company", "currency", "from_date"],
        order_by="from_date desc, creation desc",
        limit=1,
    )

    if not assignment:
        frappe.throw(
            _("No active Salary Structure Assignment was found for Employee {0} on {1}.").format(
                frappe.bold(employee), frappe.bold(as_of_date)
            )
        )

    assignment = frappe.get_doc("Salary Structure Assignment", assignment[0].name)
    salary_slip = make_salary_slip(
        source_name=assignment.salary_structure,
        employee=employee,
        posting_date=as_of_date,
        for_preview=1,
    )

    if not salary_slip:
        frappe.throw(_("Unable to calculate the employee salary for the requested date."))

    if salary_slip.get("salary_slip_based_on_timesheet"):
        frappe.throw(_("Employee Letter salary variables do not support timesheet-based salary structures."))

    earnings = _regular_components(salary_slip.get("earnings"))
    deductions = _regular_components(salary_slip.get("deductions"))
    gross_salary = flt(sum(earnings.values()))
    regular_deductions = flt(sum(deductions.values()))

    company = frappe.get_cached_doc("Company", assignment.company)
    company_meta = frappe.get_meta("Company")
    assignment_meta = frappe.get_meta("Salary Structure Assignment")

    basic_component = company.get("basic_component") if company_meta.has_field("basic_component") else None
    hra_component = company.get("hra_component") if company_meta.has_field("hra_component") else None

    basic_salary = _component_value(earnings, basic_component, ["Basic", "Basic Salary"])
    if not basic_salary:
        basic_salary = flt(assignment.base)

    housing_allowance = _assignment_or_component(
        assignment,
        assignment_meta,
        "housing_allowance",
        earnings,
        preferred_component=hra_component,
        fallback_names=["Housing Allowance", "Housing", "HRA"],
    )
    transport_allowance = _assignment_or_component(
        assignment,
        assignment_meta,
        "transport_allowance",
        earnings,
        fallback_names=["Transport Allowance", "Transportation Allowance", "Transport"],
    )
    telecom_allowance = _assignment_or_component(
        assignment,
        assignment_meta,
        "telecom_allowance",
        earnings,
        fallback_names=["Telecom Allowance", "Telephone Allowance", "Mobile Allowance"],
    )
    food_allowance = _assignment_or_component(
        assignment,
        assignment_meta,
        "food_allowance",
        earnings,
        fallback_names=["Food Allowance", "Meal Allowance"],
    )
    risk_allowance = _assignment_or_component(
        assignment,
        assignment_meta,
        "risk_allowance",
        earnings,
        fallback_names=["Risk Allowance", "Hazard Allowance"],
    )

    salary_currency = assignment.get("currency") or salary_slip.get("currency") or company.default_currency
    salary_components = dict(earnings)
    salary_components.update(deductions)

    return {
        "salary_structure_assignment": assignment.name,
        "salary_structure": assignment.salary_structure,
        "assignment_from_date": assignment.from_date,
        "salary_currency": salary_currency,
        "salary_base": flt(assignment.base),
        "basic_salary": flt(basic_salary),
        "gross_salary": gross_salary,
        "regular_deductions": regular_deductions,
        "monthly_salary": flt(gross_salary - regular_deductions),
        "housing_allowance": flt(housing_allowance),
        "transport_allowance": flt(transport_allowance),
        "telecom_allowance": flt(telecom_allowance),
        "food_allowance": flt(food_allowance),
        "risk_allowance": flt(risk_allowance),
        "earnings": earnings,
        "deductions": deductions,
        "salary_components": salary_components,
    }


def _regular_components(rows):
    values = {}
    for row in rows or []:
        if row.get("do_not_include_in_total"):
            continue
        if row.get("additional_salary"):
            continue
        component = row.get("salary_component")
        if not component:
            continue
        values[component] = flt(values.get(component)) + flt(row.get("amount"))
    return values


def _component_value(components, preferred_component=None, fallback_names=None):
    if preferred_component and preferred_component in components:
        return flt(components.get(preferred_component))

    normalized = {_normalize_component_name(k): v for k, v in (components or {}).items()}
    for name in fallback_names or []:
        value = normalized.get(_normalize_component_name(name))
        if value is not None:
            return flt(value)
    return 0.0


def _assignment_or_component(
    assignment,
    assignment_meta,
    assignment_field,
    components,
    preferred_component=None,
    fallback_names=None,
):
    component_value = _component_value(components, preferred_component, fallback_names)
    if component_value:
        return component_value

    if assignment_meta.has_field(assignment_field):
        value = flt(assignment.get(assignment_field))
        if value:
            return value
    return 0.0


def _normalize_component_name(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _file_url_to_data_uri(file_url):
    file_row = frappe.db.get_value(
        "File",
        {"file_url": file_url},
        ["name", "file_name"],
        as_dict=True,
    )
    if not file_row:
        frappe.throw(_("Unable to find attached image {0}.").format(frappe.bold(file_url)))

    file_doc = frappe.get_doc("File", file_row.name)
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()

    mime_type = mimetypes.guess_type(file_row.file_name or file_url)[0] or "image/png"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def get_permission_query_conditions(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if HR_ROLES.intersection(roles):
        return None

    if "Employee" not in roles:
        return "1=0"

    employee = _employee_for_user(user)
    if not employee:
        return "1=0"

    return "`tabEmployee Letter Request`.`employee` = {0}".format(frappe.db.escape(employee))


def has_permission(doc, user=None, ptype=None, permission_type=None, debug=False):
    user = user or frappe.session.user
    permission_type = ptype or permission_type
    roles = set(frappe.get_roles(user))
    if HR_ROLES.intersection(roles):
        return True

    if "Employee" not in roles:
        return False

    employee = _employee_for_user(user)
    if not employee:
        return False

    if permission_type == "create":
        # Frappe checks permission before before_insert(), so a brand-new ESS
        # request may not have its Employee field populated yet. Allow create
        # at the controller layer; before_insert/validate then force the request
        # to the Employee linked to the logged-in user. If a caller did send an
        # Employee explicitly, deny attempts to create for somebody else.
        return not doc or not doc.get("employee") or doc.get("employee") == employee

    if not doc:
        return False

    if doc.get("employee") != employee:
        return False

    if permission_type == "print":
        if cint(doc.get("docstatus")) != 1:
            return False

        expired = bool(doc.get("valid_until") and getdate(today()) > getdate(doc.get("valid_until")))
        if expired and doc.get("expired_document_policy") == "Block Employee Print/Download":
            return False

        # For manually signed/stamped letters the authoritative copy is the
        # uploaded PDF; the system Print Format is not an equivalent signed copy.
        if doc.get("final_document_method") == "Manual Final PDF Upload":
            return False

    return True
