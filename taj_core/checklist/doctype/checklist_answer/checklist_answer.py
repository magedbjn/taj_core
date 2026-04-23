import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_months,
    add_to_date,
    cint,
    cstr,
    flt,
    get_datetime,
    getdate,
    now_datetime,
    nowdate,
)


class ChecklistAnswer(Document):
    def before_insert(self):
        self.posting_date = self.posting_date or nowdate()
        if hasattr(self, "source_due_date") and not self.source_due_date:
            self.source_due_date = self.posting_date
        if hasattr(self, "generation_key") and not self.generation_key and getattr(self, "source_due_date", None):
            self.generation_key = build_generation_key(self.template, self.source_due_date)
        self.validate_creator()
        self.enforce_open_template_rules_before_insert()
        self.set_template_context()
        self.set_time_fields_from_template()
        self.load_questions_from_template()

    def validate(self):
        self.set_template_context()
        self.load_questions_from_template()
        sync_row_answer_fields(self)
        set_started_at_if_needed(self)
        set_expired_status_if_needed(self)
        self.set_draft_status()
        evaluate_checklist_result(self)

    def after_insert(self):
        if not getattr(self.flags, "ignore_due_date_update", False):
            update_template_next_due_date(
                template_name=self.template,
                reference_date=self.source_due_date or self.posting_date
            )

    def before_submit(self):
        sync_row_answer_fields(self)
        set_completed_time_fields(self)

        if self.status != "Auto Closed":
            validate_checklist_answer(self)

        evaluate_checklist_result(self)

        if self.status != "Auto Closed":
            self.status = "Completed"

        self.answer_by = self.answer_by or frappe.session.user
        if hasattr(self, "taken_by") and not self.taken_by:
            self.taken_by = self.answer_by

    def validate_creator(self):
        if getattr(self.flags, "from_scheduler", False):
            return

        from taj_core.checklist.permissions import is_checklist_manager

        if self.is_new() and not is_checklist_manager(frappe.session.user):
            frappe.throw(
                _("Only department manager can create a new Checklist Answer."),
                frappe.PermissionError,
            )


    def enforce_open_template_rules_before_insert(self):
        if getattr(self.flags, "from_scheduler", False):
            return

        if not self.template:
            return

        open_docs = _get_open_answer_docs(self.template)

        unanswered_open_docs = [
            doc for doc in open_docs
            if not checklist_has_any_answer(doc)
        ]

        if unanswered_open_docs:
            open_doc = unanswered_open_docs[0]
            frappe.throw(
                _("An open checklist already exists for this template without answers. Please use the existing document: {0} بتاريخ {1}").format(
                    open_doc.name,
                    getdate(open_doc.posting_date)
                )
            )

        for stale_doc in open_docs:
            _auto_close_answer_doc(stale_doc)

    def set_template_context(self):
        if not self.template:
            return

        template = frappe.db.get_value(
            "Checklist Question Template",
            self.template,
            ["department", "assigned_user", "assignment_type"],
            as_dict=True,
        )

        if not template:
            return

        # القسم يمكن تحديثه دائمًا
        self.department = template.department

        # لكن assigned_user و assignment_type
        # تُنسخ فقط عند إنشاء السجل أول مرة
        if self.is_new():
            self.assigned_user = template.assigned_user

            if frappe.get_meta(self.doctype).has_field("assignment_type"):
                self.assignment_type = template.assignment_type

    def set_time_fields_from_template(self):
        if not self.template:
            return

        template = frappe.db.get_value(
            "Checklist Question Template",
            self.template,
            ["enable_time_control", "schedule_time", "completion_window_minutes"],
            as_dict=True,
        )

        if not template or not cint(template.enable_time_control):
            self.scheduled_start_at = None
            self.deadline_at = None
            self.time_status = None
            self.delay_minutes = 0
            return

        if not template.schedule_time:
            frappe.throw(_("Schedule Time is required when Time Control is enabled."))

        if not cint(template.completion_window_minutes):
            frappe.throw(_("Completion Window Minutes is required when Time Control is enabled."))

        base_date = self.source_due_date or self.posting_date or nowdate()
        scheduled_start = get_datetime(f"{base_date} {template.schedule_time}")
        deadline = add_to_date(
            scheduled_start,
            minutes=cint(template.completion_window_minutes),
            as_datetime=True,
        )

        self.scheduled_start_at = scheduled_start
        self.deadline_at = deadline
        if not self.time_status:
            self.time_status = "On Time"
        if self.delay_minutes in (None, ""):
            self.delay_minutes = 0

    def load_questions_from_template(self, force=False):
        if not self.template:
            return

        if self.answer and not force:
            return

        build_answer_rows_from_template(self, force=force)

    def set_draft_status(self):
        if self.docstatus == 1 or self.status in ("Auto Closed", "Expired"):
            return

        has_any_answer = any(not is_blank(row.answer) for row in self.answer)
        if hasattr(self, "taken_by") and not self.taken_by and has_any_answer:
            self.taken_by = frappe.session.user
        self.status = "In Progress" if has_any_answer else "Draft"


def build_generation_key(template_name, source_due_date):
    if not template_name or not source_due_date:
        return None
    return f"{template_name}::{source_due_date}"


def _doc_cycle_date(doc):
    return getdate(getattr(doc, "source_due_date", None) or getattr(doc, "posting_date", None) or nowdate())


def checklist_has_any_answer(doc):
    return any(
        not is_blank(getattr(row, "answer", ""))
        for row in (doc.answer or [])
    )


def _get_open_answer_docs(template_name, exclude=None):
    if not template_name:
        return []

    names = frappe.get_all(
        "Checklist Answer",
        filters={
            "template": template_name,
            "docstatus": 0,
        },
        order_by="creation asc",
        pluck="name",
    )

    docs = []
    for name in names:
        if exclude and name == exclude:
            continue
        docs.append(frappe.get_doc("Checklist Answer", name))

    return docs


def _auto_close_answer_doc(doc, acting_user=None):
    if not doc or doc.docstatus == 1:
        return doc

    doc.status = "Auto Closed"
    doc.answer_by = doc.answer_by or acting_user or frappe.session.user
    doc.flags.ignore_answer_validation = True
    doc.flags.ignore_permissions = True
    doc.submit()

    return doc


def refresh_open_answer_to_new_cycle(doc, source_due_date):
    due_date = getdate(source_due_date or nowdate())

    doc.posting_date = due_date

    if hasattr(doc, "source_due_date"):
        doc.source_due_date = due_date

    if hasattr(doc, "generation_key"):
        doc.generation_key = build_generation_key(doc.template, due_date)

    if not checklist_has_any_answer(doc):
        doc.status = "Draft"
        doc.started_at = None
        doc.completed_at = None
        doc.answer_by = None

        if hasattr(doc, "taken_by") and getattr(doc, "assignment_type", None) == "Any User in Department":
            doc.taken_by = None

    doc.time_status = None
    doc.delay_minutes = 0
    doc.set_time_fields_from_template()

    return doc


def create_checklist_answer_from_template(template_name: str, source_due_date=None, ignore_permissions=False, from_scheduler=False):
    due_date = getdate(source_due_date or nowdate())
    open_docs = _get_open_answer_docs(template_name)

    same_day_open_docs = [
        doc for doc in open_docs
        if _doc_cycle_date(doc) == due_date
    ]
    if same_day_open_docs:
        existing_doc = same_day_open_docs[0]
        existing_doc.flags.reused_existing = True
        existing_doc.flags.reuse_reason = "same_day_open"
        return existing_doc

    previous_unanswered_open_docs = [
        doc for doc in open_docs
        if _doc_cycle_date(doc) != due_date and not checklist_has_any_answer(doc)
    ]
    if previous_unanswered_open_docs:
        existing_doc = previous_unanswered_open_docs[0]
        existing_doc.flags.reused_existing = True
        existing_doc.flags.reuse_reason = "previous_unanswered_open"
        return existing_doc

    for stale_doc in open_docs:
        if _doc_cycle_date(stale_doc) != due_date and checklist_has_any_answer(stale_doc):
            _auto_close_answer_doc(stale_doc)

    doc = frappe.new_doc("Checklist Answer")
    doc.template = template_name
    doc.flags.from_scheduler = from_scheduler
    doc.source_due_date = due_date
    if hasattr(doc, "generation_key"):
        doc.generation_key = build_generation_key(template_name, doc.source_due_date)

    if from_scheduler and frappe.db.has_column("Checklist Answer", "generation_key") and doc.generation_key:
        existing = frappe.db.exists("Checklist Answer", {"generation_key": doc.generation_key})
        if existing:
            existing_doc = frappe.get_doc("Checklist Answer", existing)
            existing_doc.flags.reused_existing = True
            existing_doc.flags.reuse_reason = "generation_key_match"
            return existing_doc

    if ignore_permissions:
        doc.insert(ignore_permissions=True)
    else:
        doc.insert()

    doc.flags.reused_existing = False
    doc.flags.reuse_reason = None
    return doc


def build_answer_rows_from_template(doc, force=False):
    if not doc.template:
        return

    if doc.answer and not force:
        return

    template = frappe.get_doc("Checklist Question Template", doc.template)
    doc.set("answer", [])

    child_meta = frappe.get_meta("Checklist Answer Question")

    for template_row in template.questions:
        question_doc = frappe.get_doc("Checklist Question", template_row.question)

        row = doc.append("answer", {})
        row.question = question_doc.question
        row.type = question_doc.type
        row.answer = ""

        if child_meta.has_field("question_link"):
            row.question_link = question_doc.name

        if child_meta.has_field("yes_no_answer"):
            row.yes_no_answer = ""

        if child_meta.has_field("int_answer"):
            row.int_answer = None

        if child_meta.has_field("float_answer"):
            row.float_answer = None

        if child_meta.has_field("select_answer"):
            row.select_answer = ""

        if child_meta.has_field("answer_select_options"):
            row.answer_select_options = question_doc.answer_select or ""

        if child_meta.has_field("answer_min_int"):
            row.answer_min_int = question_doc.answer_min_int
        if child_meta.has_field("answer_max_int"):
            row.answer_max_int = question_doc.answer_max_int
        if child_meta.has_field("answer_min_float"):
            row.answer_min_float = question_doc.answer_min_float
        if child_meta.has_field("answer_max_float"):
            row.answer_max_float = question_doc.answer_max_float
        if child_meta.has_field("issue_if_no"):
            row.issue_if_no = question_doc.issue_if_no
        if child_meta.has_field("issue_select_values"):
            row.issue_select_values = question_doc.issue_select_values or ""

        if child_meta.has_field("has_issue"):
            row.has_issue = 0

        if child_meta.has_field("issue_note"):
            row.issue_note = ""


def sync_row_answer_fields(doc):
    child_meta = frappe.get_meta("Checklist Answer Question")

    for row in doc.answer:
        value = ""

        if row.type == "Yes/No":
            value = cstr(getattr(row, "yes_no_answer", "")).strip()
        elif row.type == "Int":
            int_value = getattr(row, "int_answer", None)
            value = "" if int_value in (None, "") else cstr(int_value).strip()
        elif row.type == "Float":
            float_value = getattr(row, "float_answer", None)
            value = "" if float_value in (None, "") else cstr(float_value).strip()
        elif row.type == "Select":
            value = cstr(getattr(row, "select_answer", "")).strip()
        else:
            value = cstr(getattr(row, "answer", "")).strip()

        if child_meta.has_field("answer"):
            row.answer = value


def set_started_at_if_needed(doc):
    if doc.started_at:
        return

    if doc.status in ("Completed", "Auto Closed"):
        return

    has_any_answer = any(not is_blank(row.answer) for row in doc.answer)
    if has_any_answer:
        doc.started_at = now_datetime()
        if hasattr(doc, "taken_by") and not doc.taken_by:
            doc.taken_by = frappe.session.user


def set_expired_status_if_needed(doc):
    if doc.docstatus == 1:
        return

    if doc.status == "Auto Closed":
        return

    if not doc.deadline_at:
        return

    now_dt = now_datetime()

    if now_dt > doc.deadline_at:
        doc.status = "Expired"
        doc.time_status = "Overdue"

        delay_seconds = (now_dt - doc.deadline_at).total_seconds()
        doc.delay_minutes = max(int(delay_seconds // 60), 0)


def set_completed_time_fields(doc):
    completed_at = doc.completed_at or now_datetime()
    doc.completed_at = completed_at

    if not doc.started_at:
        doc.started_at = completed_at

    if hasattr(doc, "taken_by") and not doc.taken_by:
        doc.taken_by = frappe.session.user

    if not doc.deadline_at:
        doc.time_status = "On Time"
        doc.delay_minutes = 0
        return

    if completed_at <= doc.deadline_at:
        doc.time_status = "On Time"
        doc.delay_minutes = 0
        return

    delay_seconds = (completed_at - doc.deadline_at).total_seconds()
    delay_minutes = int(delay_seconds // 60)

    doc.time_status = "Overdue"
    doc.delay_minutes = max(delay_minutes, 0)


def validate_checklist_answer(doc):
    if getattr(doc.flags, "ignore_answer_validation", False):
        return

    if doc.status == "Auto Closed":
        return

    if not doc.answer:
        frappe.throw(_("No checklist questions were loaded."))

    for idx, row in enumerate(doc.answer, start=1):
        meta = get_question_meta(row)
        question_label = meta.question_text or row.question or _("Row {0}").format(idx)
        answer_value = normalize_answer(row.answer)

        if is_blank(answer_value):
            frappe.throw(_("Please answer question #{0}: {1}").format(idx, question_label))

        validate_answer_value(
            idx=idx,
            question_label=question_label,
            answer_value=answer_value,
            meta=meta,
        )


def validate_answer_value(idx, question_label, answer_value, meta):
    question_type = cstr(meta.type).strip()

    if question_type == "Yes/No":
        if answer_value not in ("Yes", "No"):
            frappe.throw(_("Question #{0}: {1} must be Yes or No.").format(idx, question_label))
    elif question_type == "Int":
        try:
            int(answer_value)
        except ValueError:
            frappe.throw(_("Question #{0}: {1} must be an integer.").format(idx, question_label))
    elif question_type == "Float":
        try:
            float(answer_value)
        except ValueError:
            frappe.throw(_("Question #{0}: {1} must be a number.").format(idx, question_label))
    elif question_type == "Select":
        options = [opt.strip() for opt in cstr(meta.answer_select).splitlines() if opt and opt.strip()]
        if options and answer_value not in options:
            frappe.throw(_("Question #{0}: {1} must be one of: {2}").format(idx, question_label, ", ".join(options)))


def evaluate_checklist_result(doc):
    has_any_issue = False
    child_meta = frappe.get_meta("Checklist Answer Question")
    parent_meta = frappe.get_meta("Checklist Answer")

    for row in doc.answer:
        meta = get_question_meta(row)
        answer_value = normalize_answer(row.answer)

        row_has_issue = 0
        row_issue_note = ""

        if not is_blank(answer_value):
            row_has_issue, row_issue_note = evaluate_row_issue(answer_value, meta)

        if child_meta.has_field("has_issue"):
            row.has_issue = 1 if row_has_issue else 0

        if child_meta.has_field("issue_note"):
            row.issue_note = row_issue_note if row_has_issue else ""

        if row_has_issue:
            has_any_issue = True

    if parent_meta.has_field("result_status"):
        doc.result_status = "Has Issue" if has_any_issue else "Normal"


def evaluate_row_issue(answer_value, meta):
    question_type = cstr(meta.type).strip()

    if question_type == "Yes/No":
        issue_if_no = cint(meta.issue_if_no or 0)
        if issue_if_no and answer_value == "No":
            return True, _("Issue because answer is No")
        return False, ""

    if question_type == "Int":
        try:
            parsed_value = int(answer_value)
        except ValueError:
            return False, ""
        min_int = meta.answer_min_int
        max_int = meta.answer_max_int
        if min_int not in (None, "") and parsed_value < cint(min_int):
            return True, _("Value is below minimum allowed")
        if max_int not in (None, "") and parsed_value > cint(max_int):
            return True, _("Value is above maximum allowed")
        return False, ""

    if question_type == "Float":
        try:
            parsed_value = float(answer_value)
        except ValueError:
            return False, ""
        min_float = meta.answer_min_float
        max_float = meta.answer_max_float
        if min_float not in (None, "") and parsed_value < flt(min_float):
            return True, _("Value is below minimum allowed")
        if max_float not in (None, "") and parsed_value > flt(max_float):
            return True, _("Value is above maximum allowed")
        return False, ""

    if question_type == "Select":
        issue_values = [opt.strip() for opt in cstr(meta.issue_select_values).splitlines() if opt and opt.strip()]
        if issue_values and answer_value in issue_values:
            return True, _("Issue option selected")
        return False, ""

    return False, ""


def get_question_meta(row):
    meta = frappe._dict({
        "question_text": row.question,
        "type": getattr(row, "type", None),
        "answer_select": getattr(row, "answer_select_options", None),
        "answer_min_int": getattr(row, "answer_min_int", None),
        "answer_max_int": getattr(row, "answer_max_int", None),
        "answer_min_float": getattr(row, "answer_min_float", None),
        "answer_max_float": getattr(row, "answer_max_float", None),
        "issue_if_no": getattr(row, "issue_if_no", 0),
        "issue_select_values": getattr(row, "issue_select_values", None),
    })

    if not row.question:
        return meta

    if (
        getattr(row, "answer_min_int", None) not in (None, "")
        or getattr(row, "answer_max_int", None) not in (None, "")
        or getattr(row, "answer_min_float", None) not in (None, "")
        or getattr(row, "answer_max_float", None) not in (None, "")
        or getattr(row, "issue_if_no", None) not in (None, "")
        or getattr(row, "issue_select_values", None) not in (None, "")
    ):
        return meta

    question_meta = frappe.get_meta("Checklist Question")
    columns = ["question", "type", "answer_select", "answer_min_int", "answer_max_int", "answer_min_float", "answer_max_float"]

    if question_meta.has_field("issue_if_no"):
        columns.append("issue_if_no")
    if question_meta.has_field("issue_select_values"):
        columns.append("issue_select_values")

    live_question = frappe.db.get_value("Checklist Question", {"question": row.question}, columns, as_dict=True)
    if live_question:
        meta.question_text = live_question.question
        meta.type = row.type or live_question.type
        meta.answer_select = getattr(row, "answer_select_options", None) or live_question.answer_select
        meta.answer_min_int = live_question.answer_min_int
        meta.answer_max_int = live_question.answer_max_int
        meta.answer_min_float = live_question.answer_min_float
        meta.answer_max_float = live_question.answer_max_float
        meta.issue_if_no = getattr(live_question, "issue_if_no", 0)
        meta.issue_select_values = getattr(live_question, "issue_select_values", None)

    return meta


def auto_close_open_answers(template_name, exclude=None):
    if not template_name:
        return

    for old_doc in _get_open_answer_docs(template_name, exclude=exclude):
        _auto_close_answer_doc(old_doc)


def update_template_next_due_date(template_name, reference_date=None):
    if not template_name:
        return

    template = frappe.get_doc("Checklist Question Template", template_name)
    periodicity = cstr(template.periodicity or "None").strip()
    base_date = getdate(reference_date or nowdate())

    if periodicity == "None":
        next_due_date = None
    elif periodicity == "Daily":
        next_due_date = add_days(base_date, 1)
    elif periodicity == "Weekly":
        next_due_date = add_days(base_date, 7)
    elif periodicity == "Monthly":
        next_due_date = add_months(base_date, 1)
    else:
        next_due_date = None

    template.db_set("next_due_date", next_due_date, update_modified=False)


def normalize_answer(value):
    if value is None:
        return ""
    return cstr(value).strip()


def is_blank(value):
    return normalize_answer(value) == ""
