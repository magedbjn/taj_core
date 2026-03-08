import json
import frappe
from frappe import _
from frappe.utils import getdate, nowdate
from erpnext.manufacturing.doctype.job_card.job_card import JobCard as ERPNextJobCard


def _get_work_order_state(work_order_name: str) -> dict:
    if not work_order_name:
        return {}

    return frappe.db.get_value(
        "Work Order",
        work_order_name,
        ["status", "skip_transfer", "planned_start_date"],
        as_dict=True
    ) or {}


def _check_planned_start_date(wo: dict, reference_date):
    """
    Block starting work BEFORE Work Order planned_start_date.
    reference_date is a DATE (not datetime).
    """
    planned = wo.get("planned_start_date")
    if not planned:
        return  # no planned date, no restriction

    planned_date = getdate(planned)
    ref_date = getdate(reference_date)

    # Block ONLY if trying to start before planned date
    if ref_date < planned_date:
        frappe.throw(
            _("This job can start on {0} (Work Order Planned Start Date).").format(
                frappe.format_value(planned_date, {"fieldtype": "Date"})
            )
        )


def _raise_if_blocked(wo: dict, *, allow_draft_save: bool, check_planned_date: bool, reference_date=None):
    """
    Strict gate rules:
    - Closed / Stopped: block everything
    - Not Started + skip_transfer == 0: block actions/submit (draft save can be allowed)
    - Planned Start Date: block actions if before planned_start_date
    """
    status = (wo.get("status") or "").strip()
    skip_transfer = int(wo.get("skip_transfer") or 0)

    # 1) Closed / Stopped => block everything
    if status in ("Closed", "Stopped"):
        frappe.throw(_("Work Order is {0}. No actions are allowed.").format(status))

    # 2) Not Started + skip_transfer == 0
    if status == "Not Started" and skip_transfer == 0:
        if not allow_draft_save:
            frappe.throw(_("Work Order is Not Started."))

    # 3) Planned Start Date restriction (apply to actions only)
    if check_planned_date:
        if reference_date is None:
            reference_date = getdate(nowdate())
        _check_planned_start_date(wo, reference_date)


class CustomJobCard(ERPNextJobCard):
    def _get_reference_date_for_start(self):
        if self.actual_start_date:
            return getdate(self.actual_start_date)
        return getdate(nowdate())

    def _gate_for_action(self):
        if not self.work_order:
            return
        wo = _get_work_order_state(self.work_order)
        ref_date = self._get_reference_date_for_start()
        _raise_if_blocked(wo, allow_draft_save=False, check_planned_date=True, reference_date=ref_date)

    def _gate_for_submit(self):
        if not self.work_order:
            return
        wo = _get_work_order_state(self.work_order)
        _raise_if_blocked(wo, allow_draft_save=False, check_planned_date=False)

    def _gate_for_save(self):
        if not self.work_order:
            return
        wo = _get_work_order_state(self.work_order)
        _raise_if_blocked(wo, allow_draft_save=True, check_planned_date=False)

    def validate(self):
        """
        validate() runs for BOTH:
        - draft save (docstatus=0)
        - submit flow (docstatus is set to 1 before validate in many Frappe flows)
        """
        if self.docstatus == 0:
            self._gate_for_save()      # allow draft save (except Closed/Stopped)
        else:
            self._gate_for_submit()    # strict block on submit

        return super().validate()

    # Operational methods (UI + API safe)
    def start_timer(self, **kwargs):
        self._gate_for_action()
        return super().start_timer(**kwargs)

    def pause_job(self, **kwargs):
        self._gate_for_action()
        return super().pause_job(**kwargs)

    def resume_job(self, **kwargs):
        self._gate_for_action()
        return super().resume_job(**kwargs)

    def complete_job_card(self, **kwargs):
        self._gate_for_action()
        return super().complete_job_card(**kwargs)

    def add_time_log(self, args):
        self._gate_for_action()
        return super().add_time_log(args)

    def add_time_logs(self, **kwargs):
        self._gate_for_action()
        return super().add_time_logs(**kwargs)
@frappe.whitelist()
def make_time_log_strict(args=None, kwargs=None, **rest):
    """
    Strict override for ERPNext make_time_log.
    Blocks time logging via API too, including planned_start_date rule.
    """
    payload = args or kwargs or rest.get("args") or rest.get("kwargs")
    if payload is None:
        frappe.throw(_("Missing arguments for make_time_log"))

    if isinstance(payload, str):
        payload = json.loads(payload)

    payload = frappe._dict(payload)
    job_card_id = payload.get("job_card_id") or payload.get("job_card") or payload.get("name")
    if not job_card_id:
        frappe.throw(_("Missing job_card_id"))

    jc = frappe.db.get_value("Job Card", job_card_id, ["work_order", "actual_start_date"], as_dict=True) or {}
    wo = _get_work_order_state(jc.get("work_order"))

    # Use JC actual_start_date if exists, else today's date
    ref_date = getdate(jc.get("actual_start_date")) if jc.get("actual_start_date") else getdate(nowdate())

    _raise_if_blocked(
        wo,
        allow_draft_save=False,
        check_planned_date=True,
        reference_date=ref_date
    )

    doc = frappe.get_doc("Job Card", job_card_id)
    doc.validate_sequence_id()
    doc.add_time_log(payload)
    doc.set_status(update_status=True)
    return {"ok": True}