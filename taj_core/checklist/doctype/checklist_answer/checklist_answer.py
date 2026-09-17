import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days,
    add_months,
    add_to_date,
    cint,
    cstr,
    get_datetime,
    getdate,
    now_datetime,
    nowdate,
)

from taj_core.checklist.rules import (
    calculate_schedule_due_date,
    classify_auto_close_status,
    evaluate_issue as evaluate_issue_rule,
    is_valid_answer,
    is_before_scheduled_start,
    normalize_multi_value,
    next_week_of_month_due_date,
    stable_generation_key,
    should_reuse_manual_open_checklist,
    should_reuse_open_checklist,
    summarize_required_answers,
    summarize_workers,
)


class ChecklistAnswer(Document):
    def before_insert(self):
        self.posting_date = self.posting_date or nowdate()
        if hasattr(self, "source_due_date") and not self.source_due_date:
            self.source_due_date = self.posting_date
        if hasattr(self, "generation_key") and not self.generation_key and getattr(self, "source_due_date", None):
            self.generation_key = build_generation_key(
                self.template,
                self.source_due_date,
                schedule_name=getattr(self, "schedule", None),
            )
        self.validate_creator()
        self.enforce_open_template_rules_before_insert()
        self.set_template_context()
        self.set_time_fields_from_template()
        self.load_questions_from_template()

    def validate(self):
        self.set_template_context()
        self.validate_schedule_identity()
        self.load_questions_from_template()
        sync_row_answer_fields(self)
        sync_worker_rows(self)
        validate_worker_rows(self)
        update_worker_summary(self)
        set_started_at_if_needed(self)
        set_expired_status_if_needed(self)
        self.set_draft_status()
        evaluate_checklist_result(self)

    def after_insert(self):
        if getattr(self.flags, "ignore_due_date_update", False):
            return
        if getattr(self, "schedule", None):
            update_schedule_next_due_date(
                schedule_name=self.schedule,
                reference_date=self.source_due_date or self.posting_date,
            )
        else:
            update_template_next_due_date(
                template_name=self.template,
                reference_date=self.source_due_date or self.posting_date,
            )

    def before_submit(self):
        validate_scheduled_start_reached(self)
        sync_row_answer_fields(self)
        sync_worker_rows(self)
        validate_worker_rows(self)
        update_worker_summary(self)
        set_completed_time_fields(self)

        if self.status not in ("Auto Closed", "Auto Closed - Incomplete", "Missed"):
            validate_checklist_answer(self)

        evaluate_checklist_result(self)

        if self.status not in ("Auto Closed", "Auto Closed - Incomplete", "Missed"):
            self.status = "Completed"

        if self.status not in ("Auto Closed", "Auto Closed - Incomplete", "Missed"):
            self.answer_by = self.answer_by or frappe.session.user
            if hasattr(self, "taken_by") and not self.taken_by:
                self.taken_by = self.answer_by
        elif self.status == "Auto Closed - Incomplete" and not self.answer_by:
            self.answer_by = getattr(self, "taken_by", None)

    def on_submit(self):
        if self.status != "Completed":
            return

        from taj_core.checklist.actions import process_checklist_actions
        from taj_core.checklist.notifications import notify_checklist_issues

        process_checklist_actions(self)
        notify_checklist_issues(self)

    def validate_creator(self):
        if getattr(self.flags, "from_scheduler", False):
            return

        from taj_core.checklist.permissions import is_checklist_manager

        if (
            self.is_new()
            and frappe.db.exists("DocType", "Checklist Schedule")
            and not getattr(self, "schedule", None)
        ):
            frappe.throw(
                _("Create the checklist through Checklist Schedule. Use a Manual schedule for on-demand inspections."),
                frappe.ValidationError,
            )

        if self.is_new() and not is_checklist_manager(frappe.session.user):
            frappe.throw(
                _("Only department manager can create a new Checklist Answer."),
                frappe.PermissionError,
            )

    def enforce_open_template_rules_before_insert(self):
        if getattr(self.flags, "from_scheduler", False):
            return
        if getattr(self.flags, "allow_parallel_manual_cycle", False):
            return
        if not self.template:
            return

        if getattr(self, "schedule", None):
            cycle_behavior = frappe.db.get_value("Checklist Schedule", self.schedule, "cycle_behavior") or "Fresh Every Cycle"
            open_docs = _get_open_answer_docs(self.template, schedule_name=self.schedule)
        else:
            cycle_behavior = frappe.db.get_value("Checklist Question Template", self.template, "cycle_behavior") or "Fresh Every Cycle"
            open_docs = _get_open_answer_docs(self.template)

        due_date = getdate(getattr(self, "source_due_date", None) or getattr(self, "posting_date", None) or nowdate())
        for open_doc in open_docs:
            same_cycle = _doc_cycle_date(open_doc) == due_date
            if should_reuse_open_checklist(cycle_behavior, same_cycle=same_cycle):
                frappe.throw(
                    _("An open checklist already exists for this template: {0} dated {1}").format(
                        open_doc.name, getdate(open_doc.posting_date)
                    )
                )
            _auto_close_answer_doc(open_doc)

    def validate_schedule_identity(self):
        if not getattr(self, "schedule", None):
            return

        identity_fields = ("schedule", "template", "company", "department", "plant_floor", "warehouse", "asset")

        if self.is_new():
            schedule = frappe.db.get_value(
                "Checklist Schedule",
                self.schedule,
                ["template", "company", "department", "plant_floor", "warehouse", "asset"],
                as_dict=True,
            )
            if not schedule:
                frappe.throw(_("Checklist Schedule does not exist: {0}").format(self.schedule))

            for fieldname in identity_fields[1:]:
                current = cstr(getattr(self, fieldname, None) or "").strip()
                expected = cstr(getattr(schedule, fieldname, None) or "").strip()
                if current != expected:
                    frappe.throw(
                        _("{0} does not match its Checklist Schedule.").format(fieldname.replace("_", " ").title())
                    )
            return

        previous = self.get_doc_before_save()
        if not previous:
            return
        for fieldname in identity_fields:
            current = cstr(getattr(self, fieldname, None) or "").strip()
            original = cstr(getattr(previous, fieldname, None) or "").strip()
            if current != original:
                frappe.throw(_("Checklist identity field {0} cannot be changed after creation.").format(fieldname))

    def set_template_context(self):
        if not self.template:
            return

        template = frappe.db.get_value(
            "Checklist Question Template",
            self.template,
            [
                "department", "plant_floor", "warehouse", "asset", "assigned_user", "assignment_type",
                "enable_worker_check", "required_worker_count", "default_worker_company",
                "default_worker_supplier", "worker_failure_reason_options", "cycle_behavior",
                "notify_on_overdue", "escalate_after_minutes", "escalation_user", "required_before_production",
            ],
            as_dict=True,
        )
        if not template:
            return

        schedule = None
        if getattr(self, "schedule", None):
            schedule = frappe.db.get_value(
                "Checklist Schedule",
                self.schedule,
                [
                    "company", "department", "plant_floor", "warehouse", "asset", "assigned_user",
                    "assignment_type", "cycle_behavior", "notify_on_overdue", "escalate_after_minutes",
                    "escalation_user", "required_before_production",
                ],
                as_dict=True,
            )

        if not self.is_new():
            return

        operational = schedule or template
        answer_meta = frappe.get_meta(self.doctype)
        if answer_meta.has_field("company"):
            self.company = getattr(operational, "company", None)
        self.department = getattr(operational, "department", None)
        if answer_meta.has_field("plant_floor"):
            self.plant_floor = getattr(operational, "plant_floor", None)
        if answer_meta.has_field("warehouse"):
            self.warehouse = getattr(operational, "warehouse", None)
        if answer_meta.has_field("asset"):
            self.asset = getattr(operational, "asset", None)
        if answer_meta.has_field("assignment_type"):
            self.assignment_type = getattr(operational, "assignment_type", None) or "Any User in Department"
        self.assigned_user = getattr(operational, "assigned_user", None)

        if answer_meta.has_field("enable_worker_check"):
            self.enable_worker_check = cint(getattr(template, "enable_worker_check", 0))
            self.required_worker_count = cint(getattr(template, "required_worker_count", 0))
            self.default_worker_company = cstr(getattr(template, "default_worker_company", "") or "").strip()
            self.default_worker_supplier = getattr(template, "default_worker_supplier", None)
            self.worker_failure_reason_options = cstr(getattr(template, "worker_failure_reason_options", "") or "").strip()

        if answer_meta.has_field("cycle_behavior"):
            self.cycle_behavior = getattr(operational, "cycle_behavior", None) or "Fresh Every Cycle"
            self.notify_on_overdue = cint(getattr(operational, "notify_on_overdue", 0))
            self.escalate_after_minutes = cint(getattr(operational, "escalate_after_minutes", 0))
            self.escalation_user = getattr(operational, "escalation_user", None)
            self.required_before_production = cint(getattr(operational, "required_before_production", 0))

    def set_time_fields_from_template(self):
        if not self.template:
            return

        if getattr(self, "schedule", None):
            timing = frappe.db.get_value(
                "Checklist Schedule",
                self.schedule,
                ["enable_time_control", "schedule_time", "completion_window_minutes"],
                as_dict=True,
            )
        else:
            timing = frappe.db.get_value(
                "Checklist Question Template",
                self.template,
                ["enable_time_control", "schedule_time", "completion_window_minutes"],
                as_dict=True,
            )

        if not timing or not cint(timing.enable_time_control):
            self.scheduled_start_at = None
            self.deadline_at = None
            self.time_status = None
            self.delay_minutes = 0
            return

        if not timing.schedule_time:
            frappe.throw(_("Schedule Time is required when Time Control is enabled."))
        if not cint(timing.completion_window_minutes):
            frappe.throw(_("Completion Window Minutes is required when Time Control is enabled."))

        base_date = self.source_due_date or self.posting_date or nowdate()
        scheduled_start = get_datetime(f"{base_date} {timing.schedule_time}")
        deadline = add_to_date(scheduled_start, minutes=cint(timing.completion_window_minutes), as_datetime=True)
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
        if self.docstatus == 1 or self.status in ("Auto Closed", "Auto Closed - Incomplete", "Missed", "Expired"):
            return
        has_any_answer = any(not is_blank(row.answer) for row in self.answer)
        has_worker_activity = bool(cint(getattr(self, "enable_worker_check", 0)) and getattr(self, "workers", None))
        has_any_activity = has_any_answer or has_worker_activity
        if hasattr(self, "taken_by") and not self.taken_by and has_any_activity:
            self.taken_by = frappe.session.user
        self.status = "In Progress" if has_any_activity else "Draft"


def build_generation_key(template_name, source_due_date, schedule_name=None, cycle_token=None):
    return stable_generation_key(
        template_name,
        source_due_date,
        schedule_name=schedule_name,
        cycle_token=cycle_token,
    )


def _doc_cycle_date(doc):
    return getdate(getattr(doc, "source_due_date", None) or getattr(doc, "posting_date", None) or nowdate())


def checklist_has_any_answer(doc):
    has_answer = any(not is_blank(getattr(row, "answer", "")) for row in (doc.answer or []))
    has_workers = bool(cint(getattr(doc, "enable_worker_check", 0)) and getattr(doc, "workers", None))
    return has_answer or has_workers


def _get_open_answer_docs(template_name, schedule_name=None, exclude=None):
    if not template_name:
        return []
    filters = {"template": template_name, "docstatus": 0}
    if schedule_name:
        filters["schedule"] = schedule_name
    names = frappe.get_all("Checklist Answer", filters=filters, order_by="creation asc", pluck="name")
    docs = []
    for name in names:
        if exclude and name == exclude:
            continue
        docs.append(frappe.get_doc("Checklist Answer", name))
    return docs


def _auto_close_answer_doc(doc, acting_user=None):
    if not doc or doc.docstatus == 1:
        return doc
    answer_summary = summarize_required_answers(getattr(doc, "answer", None) or [])
    has_worker_activity = bool(cint(getattr(doc, "enable_worker_check", 0)) and getattr(doc, "workers", None))
    answered_count = answer_summary["answered"] + (1 if has_worker_activity else 0)
    total_count = answer_summary["required"] + (1 if cint(getattr(doc, "enable_worker_check", 0)) else 0)
    doc.status = classify_auto_close_status(answered_count, total_count)
    if doc.status == "Auto Closed - Incomplete" and not doc.answer_by:
        doc.answer_by = acting_user or getattr(doc, "taken_by", None)
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
        doc.generation_key = build_generation_key(
            doc.template,
            due_date,
            schedule_name=getattr(doc, "schedule", None),
        )
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



def _insert_generated_answer(doc, ignore_permissions=False):
    try:
        if ignore_permissions:
            doc.insert(ignore_permissions=True)
        else:
            doc.insert()
    except Exception:
        if getattr(doc, "generation_key", None):
            existing = frappe.db.exists("Checklist Answer", {"generation_key": doc.generation_key})
            if existing:
                existing_doc = frappe.get_doc("Checklist Answer", existing)
                existing_doc.flags.reused_existing = True
                existing_doc.flags.reuse_reason = "generation_key_race"
                return existing_doc
        raise

    doc.flags.reused_existing = False
    doc.flags.reuse_reason = None
    return doc

def create_checklist_answer_from_template(template_name: str, source_due_date=None, ignore_permissions=False, from_scheduler=False):
    due_date = getdate(source_due_date or nowdate())
    cycle_behavior = frappe.db.get_value("Checklist Question Template", template_name, "cycle_behavior") or "Fresh Every Cycle"
    open_docs = _get_open_answer_docs(template_name)
    same_cycle_open_docs = [doc for doc in open_docs if _doc_cycle_date(doc) == due_date]
    if same_cycle_open_docs:
        existing_doc = same_cycle_open_docs[0]
        existing_doc.flags.reused_existing = True
        existing_doc.flags.reuse_reason = "same_day_open"
        if from_scheduler:
            update_template_next_due_date(template_name, due_date)
        return existing_doc
    previous_open_docs = [doc for doc in open_docs if _doc_cycle_date(doc) != due_date]
    if previous_open_docs and should_reuse_open_checklist(cycle_behavior, same_cycle=False):
        existing_doc = previous_open_docs[0]
        existing_doc.flags.reused_existing = True
        existing_doc.flags.reuse_reason = "continue_until_completed"
        if from_scheduler:
            update_template_next_due_date(template_name, due_date)
        return existing_doc
    for stale_doc in previous_open_docs:
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
            if from_scheduler:
                update_template_next_due_date(template_name, due_date)
            return existing_doc
    return _insert_generated_answer(doc, ignore_permissions=ignore_permissions)


def create_checklist_answer_from_schedule(schedule_name: str, source_due_date=None, ignore_permissions=False, from_scheduler=False):
    schedule = frappe.get_doc("Checklist Schedule", schedule_name)
    due_date = getdate(source_due_date or schedule.next_due_date or nowdate())
    cycle_behavior = schedule.cycle_behavior or "Fresh Every Cycle"
    is_manual_schedule = (schedule.schedule_type or "Manual").strip() == "Manual"
    open_docs = _get_open_answer_docs(schedule.template, schedule_name=schedule.name)

    if is_manual_schedule:
        if open_docs and should_reuse_manual_open_checklist(cycle_behavior):
            existing_doc = open_docs[0]
            existing_doc.flags.reused_existing = True
            existing_doc.flags.reuse_reason = "continue_until_completed"
            return existing_doc
    else:
        same_cycle_open_docs = [doc for doc in open_docs if _doc_cycle_date(doc) == due_date]
        if same_cycle_open_docs:
            existing_doc = same_cycle_open_docs[0]
            existing_doc.flags.reused_existing = True
            existing_doc.flags.reuse_reason = "same_day_open"
            if from_scheduler:
                update_schedule_next_due_date(schedule.name, due_date)
            return existing_doc
        previous_open_docs = [doc for doc in open_docs if _doc_cycle_date(doc) != due_date]
        if previous_open_docs and should_reuse_open_checklist(cycle_behavior, same_cycle=False):
            existing_doc = previous_open_docs[0]
            existing_doc.flags.reused_existing = True
            existing_doc.flags.reuse_reason = "continue_until_completed"
            if from_scheduler:
                update_schedule_next_due_date(schedule.name, due_date)
            return existing_doc
        for stale_doc in previous_open_docs:
            _auto_close_answer_doc(stale_doc)

    doc = frappe.new_doc("Checklist Answer")
    doc.schedule = schedule.name
    doc.template = schedule.template
    doc.flags.from_scheduler = from_scheduler
    doc.flags.allow_parallel_manual_cycle = bool(is_manual_schedule and not should_reuse_manual_open_checklist(cycle_behavior))
    doc.source_due_date = due_date
    manual_cycle_token = secrets.token_hex(16) if is_manual_schedule else None
    if hasattr(doc, "generation_key"):
        doc.generation_key = build_generation_key(
            schedule.template,
            due_date,
            schedule_name=schedule.name,
            cycle_token=manual_cycle_token,
        )
    if frappe.db.has_column("Checklist Answer", "generation_key") and doc.generation_key:
        existing = frappe.db.exists("Checklist Answer", {"generation_key": doc.generation_key})
        if existing:
            existing_doc = frappe.get_doc("Checklist Answer", existing)
            existing_doc.flags.reused_existing = True
            existing_doc.flags.reuse_reason = "generation_key_match"
            if from_scheduler:
                update_schedule_next_due_date(schedule.name, due_date)
            return existing_doc
    return _insert_generated_answer(doc, ignore_permissions=ignore_permissions)

def build_answer_rows_from_template(doc, force=False):
    if not doc.template:
        return

    if doc.answer and not force:
        return

    template = frappe.get_doc("Checklist Question Template", doc.template)
    doc.set("answer", [])

    child_meta = frappe.get_meta("Checklist Answer Question")
    snapshot_fields = (
        "question_group",
        "standard_reference",
        "is_required",
        "quick_pass_allowed",
        "answer_min_int",
        "answer_max_int",
        "answer_min_float",
        "answer_max_float",
        "issue_if_no",
        "issue_select_values",
        "issue_severity",
        "quality_impact",
        "require_failure_reason",
        "failure_reason_options",
        "require_affected_item",
        "affected_item_options",
        "require_issue_type",
        "issue_type_options",
        "require_failure_note",
        "require_failure_photo",
        "allow_no_photo_with_reason",
        "require_follow_up",
        "responsible_department",
        "responsible_user",
        "notify_department",
        "notify_user",
        "require_verification",
    )

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
        if child_meta.has_field("pass_fail_answer"):
            row.pass_fail_answer = ""
        if child_meta.has_field("int_answer"):
            row.int_answer = None
        if child_meta.has_field("float_answer"):
            row.float_answer = None
        if child_meta.has_field("select_answer"):
            row.select_answer = ""
        if child_meta.has_field("multi_select_answer"):
            row.multi_select_answer = ""
        if child_meta.has_field("text_answer"):
            row.text_answer = ""
        if child_meta.has_field("photo_answer"):
            row.photo_answer = ""

        if child_meta.has_field("answer_select_options"):
            row.answer_select_options = question_doc.answer_select or ""

        for fieldname in snapshot_fields:
            if child_meta.has_field(fieldname):
                value = getattr(question_doc, fieldname, None)
                if fieldname == "is_required" and value in (None, ""):
                    value = 1
                if fieldname == "issue_severity" and not value:
                    value = "Medium"
                setattr(row, fieldname, value)

        if child_meta.has_field("has_issue"):
            row.has_issue = 0
        if child_meta.has_field("issue_note"):
            row.issue_note = ""
        if child_meta.has_field("failure_reason"):
            row.failure_reason = ""
        if child_meta.has_field("affected_items"):
            row.affected_items = ""
        if child_meta.has_field("issue_type"):
            row.issue_type = ""
        if child_meta.has_field("user_note"):
            row.user_note = ""
        if child_meta.has_field("evidence_photo"):
            row.evidence_photo = ""
        if child_meta.has_field("photo_unavailable_reason"):
            row.photo_unavailable_reason = ""

def sync_row_answer_fields(doc):
    child_meta = frappe.get_meta("Checklist Answer Question")

    for row in doc.answer:
        value = ""
        question_type = cstr(row.type).strip()

        if question_type in ("Yes/No", "Yes/No/NA"):
            value = cstr(getattr(row, "yes_no_answer", "")).strip()
        elif question_type == "Pass/Fail/NA":
            value = cstr(getattr(row, "pass_fail_answer", "")).strip()
        elif question_type == "Int":
            int_value = getattr(row, "int_answer", None)
            value = "" if int_value in (None, "") else cstr(int_value).strip()
        elif question_type == "Float":
            float_value = getattr(row, "float_answer", None)
            value = "" if float_value in (None, "") else cstr(float_value).strip()
        elif question_type in ("Select", "Single Select"):
            value = cstr(getattr(row, "select_answer", "")).strip()
        elif question_type == "Multi Select":
            value = normalize_multi_value(getattr(row, "multi_select_answer", ""))
        elif question_type == "Text":
            value = cstr(getattr(row, "text_answer", "")).strip()
        elif question_type == "Photo":
            value = cstr(getattr(row, "photo_answer", "")).strip()
        else:
            value = cstr(getattr(row, "answer", "")).strip()

        if child_meta.has_field("answer"):
            row.answer = value

def validate_scheduled_start_reached(doc, now_value=None):
    scheduled_start = get_datetime(doc.scheduled_start_at) if getattr(doc, "scheduled_start_at", None) else None
    if not scheduled_start:
        return

    now_dt = now_value or now_datetime()
    if is_before_scheduled_start(scheduled_start, now_dt):
        frappe.throw(
            _("Checklist cannot be started before its scheduled start time: {0}.").format(
                scheduled_start
            )
        )


def set_started_at_if_needed(doc):
    if doc.started_at:
        return

    if doc.status in ("Completed", "Auto Closed"):
        return

    has_activity = checklist_has_any_answer(doc)
    if not has_activity:
        return

    now_dt = now_datetime()
    validate_scheduled_start_reached(doc, now_value=now_dt)

    doc.started_at = now_dt
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
        if getattr(doc, "time_status", None) != "Escalated":
            doc.time_status = "Overdue"

        delay_seconds = (now_dt - doc.deadline_at).total_seconds()
        doc.delay_minutes = max(int(delay_seconds // 60), 0)


def set_completed_time_fields(doc):
    completed_at = doc.completed_at or now_datetime()
    doc.completed_at = completed_at

    if doc.status == "Missed":
        if not doc.deadline_at:
            doc.time_status = "Overdue"
            doc.delay_minutes = 0
            return
        delay_seconds = (completed_at - doc.deadline_at).total_seconds()
        doc.time_status = "Overdue" if delay_seconds > 0 else "On Time"
        doc.delay_minutes = max(int(delay_seconds // 60), 0) if delay_seconds > 0 else 0
        return

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
            if cint(getattr(meta, "is_required", 1)):
                frappe.throw(_("Please answer question #{0}: {1}").format(idx, question_label))
            continue

        validate_answer_value(
            idx=idx,
            question_label=question_label,
            answer_value=answer_value,
            meta=meta,
        )

        row_has_issue, _issue_note = evaluate_row_issue(answer_value, meta)
        if row_has_issue:
            validate_failure_details(idx, question_label, row, meta)


def validate_failure_details(idx, question_label, row, meta):
    failure_reason = cstr(getattr(row, "failure_reason", "")).strip()
    affected_items = normalize_multi_value(getattr(row, "affected_items", ""))
    issue_type = cstr(getattr(row, "issue_type", "")).strip()
    user_note = cstr(getattr(row, "user_note", "")).strip()

    if cint(getattr(meta, "require_failure_reason", 0)) and not failure_reason:
        frappe.throw(_("Question #{0}: {1} requires a failure reason.").format(idx, question_label))

    reason_options = [
        option.strip()
        for option in cstr(getattr(meta, "failure_reason_options", "")).splitlines()
        if option and option.strip()
    ]
    if failure_reason and reason_options and failure_reason not in reason_options:
        frappe.throw(_("Question #{0}: {1} has an invalid failure reason.").format(idx, question_label))

    affected_values = [value.strip() for value in cstr(affected_items).splitlines() if value and value.strip()]
    if cint(getattr(meta, "require_affected_item", 0)) and not affected_values:
        frappe.throw(_("Question #{0}: {1} requires an affected item.").format(idx, question_label))

    affected_options = [
        option.strip()
        for option in cstr(getattr(meta, "affected_item_options", "")).splitlines()
        if option and option.strip()
    ]
    invalid_affected = [value for value in affected_values if affected_options and value not in affected_options]
    if invalid_affected:
        frappe.throw(_("Question #{0}: {1} has an invalid affected item: {2}.").format(
            idx, question_label, ", ".join(invalid_affected)
        ))

    if cint(getattr(meta, "require_issue_type", 0)) and not issue_type:
        frappe.throw(_("Question #{0}: {1} requires an issue type.").format(idx, question_label))

    issue_type_options = [
        option.strip()
        for option in cstr(getattr(meta, "issue_type_options", "")).splitlines()
        if option and option.strip()
    ]
    if issue_type and issue_type_options and issue_type not in issue_type_options:
        frappe.throw(_("Question #{0}: {1} has an invalid issue type.").format(idx, question_label))

    if cint(getattr(meta, "require_failure_note", 0)) and not user_note:
        frappe.throw(_("Question #{0}: {1} requires a note for the failure.").format(idx, question_label))

def validate_answer_value(idx, question_label, answer_value, meta):
    question_type = cstr(meta.type).strip()
    answer_options = cstr(getattr(meta, "answer_select", "") or "")

    if is_valid_answer(answer_value, question_type, answer_options):
        return

    if question_type == "Yes/No":
        frappe.throw(_("Question #{0}: {1} must be Yes or No.").format(idx, question_label))
    if question_type == "Yes/No/NA":
        frappe.throw(_("Question #{0}: {1} must be Yes, No, or N/A.").format(idx, question_label))
    if question_type == "Pass/Fail/NA":
        frappe.throw(_("Question #{0}: {1} must be Pass, Fail, or N/A.").format(idx, question_label))
    if question_type == "Int":
        frappe.throw(_("Question #{0}: {1} must be an integer.").format(idx, question_label))
    if question_type == "Float":
        frappe.throw(_("Question #{0}: {1} must be a number.").format(idx, question_label))
    if question_type in ("Select", "Single Select", "Multi Select"):
        options = [opt.strip() for opt in answer_options.splitlines() if opt and opt.strip()]
        frappe.throw(_("Question #{0}: {1} must use configured options: {2}").format(idx, question_label, ", ".join(options)))

def sync_worker_rows(doc):
    if not cint(getattr(doc, "enable_worker_check", 0)):
        return

    for row in getattr(doc, "workers", None) or []:
        worker_type = cstr(getattr(row, "worker_type", "") or "").strip()

        if worker_type == "Internal Employee":
            if not getattr(row, "employee", None):
                frappe.throw(_("Employee is required for an internal worker row."))

            employee = frappe.db.get_value(
                "Employee",
                row.employee,
                ["employee_name", "company"],
                as_dict=True,
            )
            if not employee:
                frappe.throw(_("Employee {0} was not found.").format(row.employee))

            row.external_worker = None
            row.worker_name = employee.employee_name or row.employee
            row.company_name = employee.company or ""
            if hasattr(row, "supplier"):
                row.supplier = None
            if hasattr(row, "badge_no"):
                row.badge_no = ""

        elif worker_type == "External Worker":
            if not getattr(row, "external_worker", None):
                frappe.throw(_("External Worker is required for an external worker row."))

            worker = frappe.db.get_value(
                "Checklist External Worker",
                row.external_worker,
                ["worker_name", "company_name", "supplier", "badge_no"],
                as_dict=True,
            )
            if not worker:
                frappe.throw(_("External Worker {0} was not found.").format(row.external_worker))

            row.employee = None
            row.worker_name = worker.worker_name
            row.company_name = worker.company_name or ""
            if hasattr(row, "supplier"):
                row.supplier = worker.supplier
            if hasattr(row, "badge_no"):
                row.badge_no = worker.badge_no or ""

        else:
            frappe.throw(_("Worker Type must be Internal Employee or External Worker."))

        if not getattr(row, "presence_status", None):
            row.presence_status = "Present"

        if row.presence_status not in ("Present", "Absent"):
            frappe.throw(_("Worker presence must be Present or Absent."))

        if getattr(row, "inspection_status", None) not in (None, "", "Pass", "Fail", "N/A"):
            frappe.throw(_("Worker inspection must be Pass, Fail, or N/A."))

        if getattr(row, "inspection_status", None) != "Fail":
            row.failure_reasons = ""
            row.note = cstr(getattr(row, "note", "") or "").strip()
            row.corrected_immediately = 0


def validate_worker_rows(doc):
    if not cint(getattr(doc, "enable_worker_check", 0)):
        return

    seen = set()
    for row in getattr(doc, "workers", None) or []:
        if row.worker_type == "Internal Employee":
            key = ("Internal Employee", cstr(row.employee))
        else:
            key = ("External Worker", cstr(row.external_worker))

        if key in seen:
            frappe.throw(_("Worker {0} is listed more than once in this checklist.").format(row.worker_name or key[1]))
        seen.add(key)


def update_worker_summary(doc):
    if not hasattr(doc, "enable_worker_check"):
        return

    if not cint(getattr(doc, "enable_worker_check", 0)):
        doc.present_worker_count = 0
        doc.absent_worker_count = 0
        doc.replacement_worker_count = 0
        doc.worker_shortage_count = 0
        doc.worker_requirement_status = "Not Set"
        return

    summary = summarize_workers(
        getattr(doc, "workers", None) or [],
        required_count=getattr(doc, "required_worker_count", 0),
    )
    doc.present_worker_count = summary["present"]
    doc.absent_worker_count = summary["absent"]
    doc.replacement_worker_count = summary["replacements"]
    doc.worker_shortage_count = summary["shortage"]
    doc.worker_requirement_status = summary["status"]


def evaluate_checklist_result(doc):
    has_any_issue = False
    has_critical_issue = False
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
            if cstr(getattr(meta, "issue_severity", "Medium")).strip() == "Critical":
                has_critical_issue = True
        else:
            if child_meta.has_field("failure_reason"):
                row.failure_reason = ""
            if child_meta.has_field("affected_items"):
                row.affected_items = ""
            if child_meta.has_field("issue_type"):
                row.issue_type = ""
            if child_meta.has_field("user_note"):
                row.user_note = ""
            if child_meta.has_field("evidence_photo"):
                row.evidence_photo = ""

    if cint(getattr(doc, "enable_worker_check", 0)):
        if cint(getattr(doc, "worker_shortage_count", 0)) > 0:
            has_any_issue = True
        if any(cstr(getattr(row, "inspection_status", "") or "").strip() == "Fail" for row in (getattr(doc, "workers", None) or [])):
            has_any_issue = True

    if cint(getattr(doc, "production_started_before_completion", 0)):
        has_any_issue = True

    if parent_meta.has_field("result_status"):
        if has_critical_issue:
            doc.result_status = "Critical"
        elif has_any_issue:
            doc.result_status = "Has Issue"
        else:
            doc.result_status = "Normal"

def evaluate_row_issue(answer_value, meta):
    question_type = cstr(meta.type).strip()
    min_value = None
    max_value = None

    if question_type == "Int":
        min_value = getattr(meta, "answer_min_int", None)
        max_value = getattr(meta, "answer_max_int", None)
    elif question_type == "Float":
        min_value = getattr(meta, "answer_min_float", None)
        max_value = getattr(meta, "answer_max_float", None)

    has_issue, message = evaluate_issue_rule(
        answer_value,
        question_type,
        issue_if_no=cint(getattr(meta, "issue_if_no", 0)),
        issue_select_values=getattr(meta, "issue_select_values", None),
        min_value=min_value,
        max_value=max_value,
    )
    return has_issue, _(message) if message else ""

def get_question_meta(row):
    meta = frappe._dict({
        "question_text": row.question,
        "type": getattr(row, "type", None),
        "question_group": getattr(row, "question_group", None),
        "standard_reference": getattr(row, "standard_reference", None),
        "answer_select": getattr(row, "answer_select_options", None),
        "is_required": getattr(row, "is_required", 1),
        "quick_pass_allowed": getattr(row, "quick_pass_allowed", 0),
        "answer_min_int": getattr(row, "answer_min_int", None),
        "answer_max_int": getattr(row, "answer_max_int", None),
        "answer_min_float": getattr(row, "answer_min_float", None),
        "answer_max_float": getattr(row, "answer_max_float", None),
        "issue_if_no": getattr(row, "issue_if_no", 0),
        "issue_select_values": getattr(row, "issue_select_values", None),
        "issue_severity": getattr(row, "issue_severity", None) or "Medium",
        "quality_impact": getattr(row, "quality_impact", 0),
        "require_failure_reason": getattr(row, "require_failure_reason", 0),
        "failure_reason_options": getattr(row, "failure_reason_options", None),
        "require_affected_item": getattr(row, "require_affected_item", 0),
        "affected_item_options": getattr(row, "affected_item_options", None),
        "require_issue_type": getattr(row, "require_issue_type", 0),
        "issue_type_options": getattr(row, "issue_type_options", None),
        "require_failure_note": getattr(row, "require_failure_note", 0),
        "require_failure_photo": getattr(row, "require_failure_photo", 0),
        "allow_no_photo_with_reason": getattr(row, "allow_no_photo_with_reason", 0),
        "require_follow_up": getattr(row, "require_follow_up", 0),
        "responsible_department": getattr(row, "responsible_department", None),
        "responsible_user": getattr(row, "responsible_user", None),
        "notify_department": getattr(row, "notify_department", None),
        "notify_user": getattr(row, "notify_user", None),
        "require_verification": getattr(row, "require_verification", 0),
    })

    # New checklists carry a full immutable snapshot. Older rows created before
    # this schema did not have question_link, so fall back to the live question
    # only for backward compatibility.
    if getattr(row, "question_link", None):
        return meta

    if not row.question:
        return meta

    question_meta = frappe.get_meta("Checklist Question")
    columns = [
        "question", "type", "answer_select", "answer_min_int", "answer_max_int",
        "answer_min_float", "answer_max_float", "issue_if_no", "issue_select_values",
    ]
    optional_columns = (
        "question_group", "standard_reference",
        "is_required", "quick_pass_allowed", "issue_severity", "quality_impact",
        "require_failure_reason", "failure_reason_options", "require_affected_item", "affected_item_options",
        "require_issue_type", "issue_type_options", "require_failure_note",
        "require_failure_photo", "allow_no_photo_with_reason", "require_follow_up", "responsible_department",
        "responsible_user", "notify_department", "notify_user", "require_verification",
    )
    for fieldname in optional_columns:
        if question_meta.has_field(fieldname):
            columns.append(fieldname)

    live_question = frappe.db.get_value(
        "Checklist Question",
        {"question": row.question},
        columns,
        as_dict=True,
    )
    if not live_question:
        return meta

    meta.question_text = live_question.question
    meta.type = row.type or live_question.type
    meta.answer_select = getattr(row, "answer_select_options", None) or live_question.answer_select
    for fieldname in columns:
        if fieldname in ("question", "type", "answer_select"):
            continue
        if hasattr(live_question, fieldname):
            setattr(meta, fieldname, getattr(live_question, fieldname))

    meta.is_required = getattr(meta, "is_required", 1)
    meta.issue_severity = getattr(meta, "issue_severity", None) or "Medium"
    return meta

def auto_close_open_answers(template_name, exclude=None):
    if not template_name:
        return

    for old_doc in _get_open_answer_docs(template_name, exclude=exclude):
        _auto_close_answer_doc(old_doc)


def update_schedule_next_due_date(schedule_name, reference_date=None):
    if not schedule_name:
        return

    schedule = frappe.get_doc("Checklist Schedule", schedule_name)
    base_date = getdate(reference_date or nowdate())
    next_due_date = calculate_schedule_due_date(schedule, reference_date=base_date, initial=False)
    schedule.db_set("next_due_date", next_due_date, update_modified=False)


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
    elif periodicity == "Weeks of Month":
        next_due_date = next_week_of_month_due_date(base_date, template.weeks_of_month)
    else:
        next_due_date = None

    template.db_set("next_due_date", next_due_date, update_modified=False)


def normalize_answer(value):
    if value is None:
        return ""
    return cstr(value).strip()


def is_blank(value):
    return normalize_answer(value) == ""
