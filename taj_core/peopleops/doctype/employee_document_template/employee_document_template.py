# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from taj_core.peopleops.doctype.employee_letter_signatory.employee_letter_signatory import validate_signatory_available


HR_ROLES = {"HR User", "HR Manager", "System Manager"}


class EmployeeDocumentTemplate(Document):
    def validate(self):
        self._set_company_defaults()
        self._validate_language_content()
        self._validate_table_print_style()
        self._validate_validity()
        self._validate_fee_policy()
        self._validate_signatory()
        self._validate_duplicate_policy()
        self._validate_jinja_syntax()

    def _set_company_defaults(self):
        if not self.company:
            return

        company = frappe.get_cached_doc("Company", self.company)
        if not self.letter_head:
            self.letter_head = company.default_letter_head

    def _validate_language_content(self):
        if self.language_mode not in {"Arabic Only", "English Only", "Bilingual"}:
            frappe.throw(_("Please select a valid Language Mode."))

        if self.language_mode == "Bilingual" and not self.bilingual_layout:
            self.bilingual_layout = "Side by Side"

        content_mode = self.content_mode or "Single Content"
        if content_mode == "Single Content":
            if self.language_mode in {"Arabic Only", "Bilingual"} and not _has_content(self.template_text_arabic):
                frappe.throw(_("Arabic template content is required."))
            if self.language_mode in {"English Only", "Bilingual"} and not _has_content(self.template_text_english):
                frappe.throw(_("English template content is required."))
            return

        if content_mode != "Sections":
            frappe.throw(_("Please select a valid Content Mode."))

        if not self.sections:
            frappe.throw(_("At least one Document Section is required when Content Mode is Sections."))

        for row in self.sections:
            if self.language_mode in {"English Only", "Bilingual"} and not _has_content(row.content_english):
                frappe.throw(_("Row #{0}: English Content is required.").format(row.idx))
            if self.language_mode in {"Arabic Only", "Bilingual"} and not _has_content(row.content_arabic):
                frappe.throw(_("Row #{0}: Arabic Content is required.").format(row.idx))

    def _validate_table_print_style(self):
        self.table_print_style = self.table_print_style or "Standard Borders"
        if self.table_print_style not in {"Standard Borders", "Borderless Layout"}:
            frappe.throw(_("Please select a valid Table Print Style."))

    def _validate_validity(self):
        if self.has_expiry:
            if not self.validity_days or self.validity_days <= 0:
                frappe.throw(_("Validity (Days) must be greater than zero when expiry is enabled."))

            allowed = {
                "Historical Copy with EXPIRED Watermark",
                "Block Employee Print/Download",
            }
            if self.expired_document_policy not in allowed:
                self.expired_document_policy = "Historical Copy with EXPIRED Watermark"

            # A manually signed/stamped PDF is a fixed legal/archive original.
            # We keep the original for HR audit and block employee access after expiry
            # instead of modifying or deleting the signed file.
            if self.final_document_method == "Manual Final PDF Upload":
                self.expired_document_policy = "Block Employee Print/Download"
        else:
            self.validity_days = 0
            self.expired_document_policy = None

    def _validate_fee_policy(self):
        if self.fee_policy == "No Fee":
            self.fee_amount = 0
            self.employee_fee_salary_component = None
            return

        if flt(self.fee_amount) <= 0:
            frappe.throw(_("Fee Amount must be greater than zero when a fee policy is selected."))

        if self.fee_policy == "Employee Pays" and self.employee_fee_salary_component:
            component = frappe.db.get_value(
                "Salary Component", self.employee_fee_salary_component, ["type", "disabled"], as_dict=True
            )
            if not component or component.type != "Deduction" or component.disabled:
                frappe.throw(_("Employee Fee Salary Component must be an enabled Deduction component."))
        elif self.fee_policy != "Employee Pays":
            self.employee_fee_salary_component = None

    def _validate_signatory(self):
        if not self.default_signatory:
            return

        signatory = validate_signatory_available(self.default_signatory, company=self.company)
        if signatory.company != self.company:
            frappe.throw(_("The selected signatory must belong to the same company as the template."))

    def _validate_duplicate_policy(self):
        if not self.prevent_duplicate_while_valid:
            self.duplicate_match_scope = None
            return
        if self.duplicate_match_scope not in {"Same Template", "Same Template and Recipient"}:
            self.duplicate_match_scope = "Same Template and Recipient"

    def _validate_jinja_syntax(self):
        context = _sample_context()
        values = [
            (_("English Subject"), self.letter_subject_english),
            (_("Arabic Subject"), self.letter_subject_arabic),
        ]

        if (self.content_mode or "Single Content") == "Sections":
            for row in self.sections:
                values.extend(
                    [
                        (_("Section #{0} English Title").format(row.idx), row.section_title_english),
                        (_("Section #{0} Arabic Title").format(row.idx), row.section_title_arabic),
                        (_("Section #{0} English Content").format(row.idx), row.content_english),
                        (_("Section #{0} Arabic Content").format(row.idx), row.content_arabic),
                    ]
                )
        else:
            values.extend(
                [
                    (_("English Content"), self.template_text_english),
                    (_("Arabic Content"), self.template_text_arabic),
                ]
            )

        # Frappe exposes _() as a standard Jinja global. Keep it explicitly
        # allowed so translated expressions such as {{ _(nationality, lang="ar", context="Nationality") }}
        # remain valid across supported Frappe versions.
        allowed_variables = set(context) | {"_"}
        jenv = frappe.get_jenv()

        for label, value in values:
            if not value:
                continue

            try:
                parsed = jenv.parse(value)
                from jinja2 import meta as jinja_meta

                unknown_variables = sorted(
                    jinja_meta.find_undeclared_variables(parsed) - allowed_variables
                )
                if unknown_variables:
                    frappe.throw(
                        _("Unknown template variable(s) in {0}: {1}").format(
                            frappe.bold(label),
                            ", ".join(frappe.bold(name) for name in unknown_variables),
                        )
                    )

                frappe.render_template(value, context)
            except frappe.ValidationError:
                raise
            except Exception as exc:
                frappe.throw(
                    _("Invalid template syntax in {0}: {1}").format(
                        frappe.bold(label), frappe.utils.escape_html(str(exc))
                    )
                )


@frappe.whitelist()
def get_available_variables():
    variables = [
        ("Employee", "{{ employee }}", "Employee ID"),
        ("Employee", "{{ employee_name }}", "Employee name"),
        ("Employee", "{{ employee_name_arabic }}", "Employee Arabic name"),
        ("Employee", "{{ first_name }}", "First name"),
        ("Employee", "{{ middle_name }}", "Middle name"),
        ("Employee", "{{ last_name }}", "Last name"),
        ("Employee", "{{ employee_number }}", "Employee number"),
        ("Employee", "{{ designation }}", "Designation"),
        ("Employee", "{{ job_title }}", "Job title (alias of designation)"),
        ("Employee", "{{ department }}", "Department"),
        ("Employee", "{{ branch }}", "Branch"),
        ("Employee", "{{ grade }}", "Employee grade"),
        ("Employee", "{{ employment_type }}", "Employment type"),
        ("Employee", "{{ gender }}", "Gender"),
        ("Employee", "{{ date_of_birth }}", "Date of birth"),
        ("Employee", "{{ date_of_joining }}", "Date of joining"),
        ("Employee", "{{ relieving_date }}", "Relieving / last working date"),
        ("Employee", "{{ works_since }}", "Works with the company since"),
        ("Employee", "{{ nationality }}", "Nationality"),
        ("Employee", "{{ id_number }}", "ID / Iqama number"),
        ("Employee", "{{ passport_number }}", "Passport number"),
        ("Employee", "{{ passport_valid_until }}", "Passport valid until"),
        ("Employee", "{{ short_address }}", "Employee short address"),
        ("Employee", "{{ bank_name }}", "Employee bank name"),
        ("Employee", "{{ iban }}", "Employee IBAN"),
        ("Company", "{{ company_name }}", "Company name"),
        ("Company", "{{ company_name_arabic }}", "Company Arabic name"),
        ("Company", "{{ company_cr_number }}", "Company commercial registration number"),
        ("Company", "{{ company_tax_id }}", "Company tax ID"),
        ("Company", "{{ company_country }}", "Company country"),
        ("Request", "{{ addressed_to }}", "Recipient / entity in English"),
        ("Request", "{{ addressed_to_arabic }}", "Recipient / entity in Arabic"),
        ("Request", "{{ purpose }}", "Request purpose"),
        ("Request", "{{ request_date }}", "Request date"),
        ("Request", "{{ required_by }}", "Required by date"),
        ("Request", "{{ issue_date }}", "Issue date"),
        ("Request", "{{ valid_until }}", "Expiry date"),
        ("Salary", "{{ salary_base }}", "Salary Structure Assignment base"),
        ("Salary", "{{ basic_salary }}", "Basic salary"),
        ("Salary", "{{ gross_salary }}", "Regular monthly earnings before deductions"),
        ("Salary", "{{ regular_deductions }}", "Regular structured deductions"),
        ("Salary", "{{ monthly_salary }}", "Regular earnings minus structured deductions"),
        ("Salary", "{{ net_salary }}", "Alias of monthly salary after regular structured deductions"),
        ("Salary", "{{ total_salary }}", "Alias of regular gross monthly earnings"),
        ("Salary", "{{ housing_allowance }}", "Housing allowance"),
        ("Salary", "{{ transport_allowance }}", "Transport allowance"),
        ("Salary", "{{ telecom_allowance }}", "Telecom allowance"),
        ("Salary", "{{ food_allowance }}", "Food allowance"),
        ("Salary", "{{ risk_allowance }}", "Risk allowance"),
        ("Salary", "{{ salary_currency }}", "Salary currency"),
        ("Signatory", "{{ signatory_name_english }}", "Signatory name in English"),
        ("Signatory", "{{ signatory_name_arabic }}", "Signatory name in Arabic"),
        ("Signatory", "{{ signatory_title_english }}", "Signatory title in English"),
        ("Signatory", "{{ signatory_title_arabic }}", "Signatory title in Arabic"),
    ]

    components = frappe.get_all(
        "Salary Component",
        filters={"disabled": 0},
        fields=["name", "type"],
        order_by="type asc, name asc",
    )
    salary_components = [
        {
            "category": row.type or "Salary Component",
            "token": '{{ salary_components.get("%s", 0) }}' % row.name.replace('"', '\\"'),
            "description": row.name,
        }
        for row in components
    ]

    translatable_tokens = {
        "{{ designation }}": ("designation", "Designation"),
        "{{ job_title }}": ("job_title", "Job Title"),
        "{{ department }}": ("department", "Department"),
        "{{ branch }}": ("branch", "Branch"),
        "{{ grade }}": ("grade", "Grade"),
        "{{ employment_type }}": ("employment_type", "Employment Type"),
        "{{ gender }}": ("gender", "Gender"),
        # Frappe also translates country names. Use a context for nationality so
        # a nationality adjective (for example Yemen -> يمني) is distinct from
        # the generic country-name translation (Yemen -> اليمن).
        "{{ nationality }}": ("nationality", "Nationality"),
        "{{ company_country }}": ("company_country", "Country"),
    }

    variable_rows = []
    for category, token, description in variables:
        translation_meta = translatable_tokens.get(token)
        fieldname = translation_meta[0] if translation_meta else None
        translation_context = translation_meta[1] if translation_meta else None
        token_ar = token
        if fieldname:
            token_ar = '{{ _(%s, lang="ar", context="%s") }}' % (fieldname, translation_context)

        variable_rows.append(
            {
                "category": category,
                "token": token,
                "token_en": token,
                "token_ar": token_ar,
                "translatable": bool(fieldname),
                "translation_context": translation_context,
                "description": description,
            }
        )

    return {
        "variables": variable_rows,
        "salary_components": salary_components,
    }


def _has_content(value):
    if not value:
        return False
    text = frappe.utils.strip_html(value or "").replace("&nbsp;", " ").strip()
    return bool(text)


def _sample_context():
    return {
        "employee": "HR-EMP-00001",
        "employee_name": "Employee Name",
        "employee_name_arabic": "اسم الموظف",
        "first_name": "Employee",
        "middle_name": "",
        "last_name": "Name",
        "employee_number": "00001",
        "designation": "Job Title",
        "job_title": "Job Title",
        "department": "Department",
        "branch": "Main Branch",
        "grade": "Grade",
        "employment_type": "Full-time",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2026-01-01",
        "relieving_date": "2026-09-30",
        "works_since": "2026-01-01",
        "nationality": "Saudi Arabia",
        "id_number": "0000000000",
        "passport_number": "P000000",
        "passport_valid_until": "2030-01-01",
        "short_address": "Short Address",
        "bank_name": "Bank",
        "iban": "SA0000000000000000000000",
        "company_name": "Company",
        "company_name_arabic": "الشركة",
        "company_cr_number": "0000000000",
        "company_tax_id": "000000000000000",
        "company_country": "Saudi Arabia",
        "addressed_to": "To Whom It May Concern",
        "addressed_to_arabic": "إلى من يهمه الأمر",
        "purpose": "Purpose",
        "request_date": "2026-09-27",
        "required_by": "2026-09-30",
        "issue_date": "2026-09-27",
        "valid_until": "2026-10-27",
        "salary_base": 0,
        "basic_salary": 0,
        "gross_salary": 0,
        "regular_deductions": 0,
        "monthly_salary": 0,
        "net_salary": 0,
        "total_salary": 0,
        "housing_allowance": 0,
        "transport_allowance": 0,
        "telecom_allowance": 0,
        "food_allowance": 0,
        "risk_allowance": 0,
        "salary_currency": "SAR",
        "salary_components": {},
        "signatory_name_english": "HR Manager",
        "signatory_name_arabic": "مدير الموارد البشرية",
        "signatory_title_english": "HR Manager",
        "signatory_title_arabic": "مدير الموارد البشرية",
    }


def _employee_for_user(user):
    return frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "company"],
        as_dict=True,
    )


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

    return (
        "`tabEmployee Document Template`.`is_active` = 1"
        " and `tabEmployee Document Template`.`available_for_employee_request` = 1"
        " and `tabEmployee Document Template`.`company` = {0}"
    ).format(frappe.db.escape(employee.company))


def has_permission(doc, user=None, ptype=None, permission_type=None, debug=False):
    user = user or frappe.session.user
    permission_type = ptype or permission_type
    roles = set(frappe.get_roles(user))
    if HR_ROLES.intersection(roles):
        return True

    if "Employee" not in roles:
        return False

    if not doc:
        return False

    employee = _employee_for_user(user)
    return bool(
        employee
        and doc.is_active
        and doc.available_for_employee_request
        and doc.company == employee.company
    )
