import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, now_datetime

from taj_core.checklist.action_rules import is_open_action_status, next_resolution_status
from taj_core.checklist.permissions import is_checklist_manager, _get_user_departments


class ChecklistAction(Document):
    def validate(self):
        self._sync_open_issue_key()
        self._validate_lifecycle_fields()

    def after_insert(self):
        from taj_core.checklist.action_notifications import notify_action_created

        notify_action_created(self)

    def _sync_open_issue_key(self):
        self.open_issue_key = self.issue_key if is_open_action_status(self.status) else None

    def _validate_lifecycle_fields(self):
        resolution_details = cstr(getattr(self, "resolution_details", None)).strip()
        waiting_reason = cstr(getattr(self, "waiting_reason", None)).strip()

        if self.status == "Waiting" and not waiting_reason:
            frappe.throw(_("Waiting Reason is required when an action is waiting."))

        if self.status in ("Pending Verification", "Closed") and not resolution_details:
            frappe.throw(_("What Was Done is required before resolving a Checklist Action."))

        if (
            self.status == "Closed"
            and cint(getattr(self, "requires_verification", 0))
            and not getattr(self, "verified_by", None)
        ):
            frappe.throw(_("This Checklist Action requires verification before it can be closed."))

    def _ensure_verifier(self, user=None):
        user = user or frappe.session.user
        if is_checklist_manager(user):
            return
        if getattr(self, "verification_user", None) == user:
            return
        verification_department = getattr(self, "verification_department", None)
        if verification_department and verification_department in _get_user_departments(user):
            return
        frappe.throw(_("You are not assigned to verify this Checklist Action."), frappe.PermissionError)

    @frappe.whitelist()
    def start_action(self):
        if self.status == "Closed":
            frappe.throw(_("Closed Checklist Actions cannot be restarted."))
        self.status = "In Progress"
        self.waiting_reason = None
        self.save()
        return self.status

    @frappe.whitelist()
    def set_waiting(self, reason):
        if self.status == "Closed":
            frappe.throw(_("Closed Checklist Actions cannot be changed to Waiting."))
        reason = cstr(reason).strip()
        if not reason:
            frappe.throw(_("Waiting Reason is required."))
        self.status = "Waiting"
        self.waiting_reason = reason
        self.save()
        return self.status

    @frappe.whitelist()
    def submit_resolution(self, resolution_details=None):
        if self.status == "Closed":
            frappe.throw(_("Checklist Action is already closed."))

        details = cstr(resolution_details or getattr(self, "resolution_details", None)).strip()
        if not details:
            frappe.throw(_("What Was Done is required before submitting a resolution."))

        self.resolution_details = details
        self.resolved_by = frappe.session.user
        self.resolved_at = now_datetime()
        self.waiting_reason = None
        self.status = next_resolution_status(cint(getattr(self, "requires_verification", 0)))
        self.save()

        if self.status == "Pending Verification":
            from taj_core.checklist.action_notifications import notify_action_pending_verification

            notify_action_pending_verification(self)

        return self.status

    @frappe.whitelist()
    def verify_resolution(self, accepted=1, note=None):
        if self.status != "Pending Verification":
            frappe.throw(_("Only actions Pending Verification can be verified."))

        self._ensure_verifier()
        accepted = cint(accepted)
        note = cstr(note).strip()

        if accepted:
            self.verification_note = note
            self.verified_by = frappe.session.user
            self.verified_at = now_datetime()
            self.status = "Closed"
        else:
            if not note:
                frappe.throw(_("Verification Note is required when rejecting a resolution."))
            self.verification_note = note
            self.verified_by = None
            self.verified_at = None
            self.status = "In Progress"

        self.save()
        return self.status
