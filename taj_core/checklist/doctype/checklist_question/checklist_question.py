# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from taj_core.checklist.rules import question_configuration_errors


class ChecklistQuestion(Document):
    def validate(self):
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
