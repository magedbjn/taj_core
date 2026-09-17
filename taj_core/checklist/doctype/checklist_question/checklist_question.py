# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from taj_core.checklist.rules import question_configuration_errors


class ChecklistQuestion(Document):
    def _sync_standard_reference(self):
        rows = list(self.get("standards") or [])
        if not rows:
            return

        seen = set()
        labels = []
        for row in rows:
            standard = str(getattr(row, "standard", None) or "").strip()
            reference = str(getattr(row, "reference", None) or "").strip()
            if not standard:
                continue
            if standard in seen:
                frappe.throw(_("Standard {0} can only be added once. Combine multiple clauses in the same reference field.").format(standard))
            seen.add(standard)
            labels.append(f"{standard} {reference}".strip())

        self.standard_reference = " | ".join(labels)

    def validate(self):
        self._sync_standard_reference()
        min_value = None
        max_value = None
        if self.type == "Int":
            min_value = self.answer_min_int
            max_value = self.answer_max_int
        elif self.type == "Float":
            min_value = self.answer_min_float
            max_value = self.answer_max_float

        errors = question_configuration_errors(
            self.type,
            answer_options=self.answer_select,
            issue_select_values=self.issue_select_values,
            min_value=min_value,
            max_value=max_value,
        )
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors))
