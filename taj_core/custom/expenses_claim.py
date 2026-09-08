import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import get_link_to_form, flt
from hrms.hr.doctype.expense_claim.expense_claim import (
    get_outstanding_amount_for_claim,
)

try:
    from frappe.model.workflow import get_transitions  # لمسار فريبي 15
except ImportError:
    from frappe.workflow.doctype.workflow.workflow import get_transitions  # لمسارات الإصدارات الأقدم


def _apply_transition_to_state(claim, target_state):
    """Apply an available workflow transition to the requested state."""
    transitions = get_transitions(claim)

    transition = next(
        (
            row
            for row in transitions
            if row.get("next_state") == target_state
        ),
        None,
    )

    if not transition:
        return False

    apply_workflow(
        claim,
        transition["action"],
    )
    return True


def update_expense_claim_status_on_payment(doc, method):
    """
    Hook: Called on_submit of Payment Entry or Journal Entry.
    """
    related_expense_claims = _get_related_expense_claims(doc)
    if not related_expense_claims:
        return

    updated_claims = []

    for claim_name in related_expense_claims:
        try:
            claim = frappe.get_doc(
                "Expense Claim",
                claim_name,
            )

            outstanding_amount = flt(
                get_outstanding_amount_for_claim(claim.name)
            )

            if outstanding_amount > 0:
                continue

            if claim.workflow_state == "Paid":
                continue

            # The configured workflow currently allows Paid
            # only through a valid workflow transition.
            if _apply_transition_to_state(
                claim,
                "Paid",
            ):
                updated_claims.append(claim_name)
                _publish_realtime_refresh(
                    claim_name,
                    claim.owner,
                )

        except Exception as e:
            frappe.log_error(
                title="Expense Claim Status Update Error",
                message=(
                    f"Error updating Expense Claim {claim_name} "
                    f"from {doc.doctype} {doc.name}\n\n{str(e)}"
                ),
            )

    if updated_claims:
        claims_links = [
            get_link_to_form(
                "Expense Claim",
                claim,
            )
            for claim in updated_claims
        ]

        frappe.msgprint(
            _(
                "Updated Expense Claims to Paid: {0}"
            ).format(
                ", ".join(claims_links)
            ),
            alert=True,
            indicator="green",
        )


def revert_expense_claim_status_on_cancel(doc, method):
    """
    Hook: Called on_cancel of Payment Entry or Journal Entry.

    Revert the workflow state only when the configured workflow
    exposes a valid transition back to Unpaid.
    """
    related_expense_claims = _get_related_expense_claims(doc)
    if not related_expense_claims:
        return

    reverted_claims = []

    for claim_name in related_expense_claims:
        try:
            claim = frappe.get_doc(
                "Expense Claim",
                claim_name,
            )

            outstanding_amount = flt(
                get_outstanding_amount_for_claim(claim.name)
            )

            if (
                outstanding_amount > 0
                and claim.workflow_state == "Paid"
                and _apply_transition_to_state(
                    claim,
                    "Unpaid",
                )
            ):
                reverted_claims.append(claim_name)
                _publish_realtime_refresh(
                    claim_name,
                    claim.owner,
                )

        except Exception as e:
            frappe.log_error(
                title="Expense Claim Status Revert Error",
                message=(
                    f"Error reverting Expense Claim {claim_name} "
                    f"from {doc.doctype} {doc.name}\n\n{str(e)}"
                ),
            )

    if reverted_claims:
        claims_links = [
            get_link_to_form(
                "Expense Claim",
                claim,
            )
            for claim in reverted_claims
        ]

        frappe.msgprint(
            _(
                "Reverted Expense Claims to Unpaid: {0}"
            ).format(
                ", ".join(claims_links)
            ),
            alert=True,
            indicator="yellow",
        )

def _get_related_expense_claims(doc):
    """
    Helper: extract related Expense Claim names from Payment Entry / Journal Entry
    """
    related_expense_claims = set()

    if doc.doctype == "Payment Entry":
        for ref in doc.references:
            if ref.reference_doctype == "Expense Claim" and ref.reference_name:
                related_expense_claims.add(ref.reference_name)

    elif doc.doctype == "Journal Entry":
        for acc in doc.accounts:
            if acc.reference_type == "Expense Claim" and acc.reference_name:
                related_expense_claims.add(acc.reference_name)

    return list(related_expense_claims)


def get_total_paid_amount(expense_claim_name):
    """
    Get total paid amount for an expense claim from all payment entries & journal entries
    """
    total_paid = frappe.db.sql(
        """
        SELECT SUM(allocated_amount)
        FROM `tabPayment Entry Reference`
        WHERE reference_doctype = 'Expense Claim'
          AND reference_name = %s
          AND parent IN (SELECT name FROM `tabPayment Entry` WHERE docstatus = 1)
        """,
        (expense_claim_name,),
    )

    journal_paid = frappe.db.sql(
        """
        SELECT SUM(debit)
        FROM `tabJournal Entry Account`
        WHERE reference_type = 'Expense Claim'
          AND reference_name = %s
          AND parent IN (SELECT name FROM `tabJournal Entry` WHERE docstatus = 1)
        """,
        (expense_claim_name,),
    )

    total = (total_paid[0][0] or 0) + (journal_paid[0][0] or 0)
    return total


def _publish_realtime_refresh(claim_name, user):
    """
    Helper: trigger realtime UI refresh for Expense Claim
    """
    frappe.publish_realtime(
        event="eval_js",
        message=f"frappe.set_route('Form', 'Expense Claim', '{claim_name}')",
        user=user,
    )