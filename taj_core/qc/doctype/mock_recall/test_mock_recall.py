# Copyright (c) 2026, Maged Bajandooh and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from taj_core.qc.doctype.mock_recall.mock_recall import (
    NUMERIC_FIELDS,
    SNAPSHOT_FIELDS,
    _same_value,
)


class IntegrationTestMockRecall(IntegrationTestCase):
    def test_removed_fields_are_not_server_owned(self):
        deleted = {"dispatched_qty", "attachments_note", "data_warning", "distribution_warning"}
        self.assertFalse(deleted.intersection(SNAPSHOT_FIELDS))
        self.assertFalse(deleted.intersection(NUMERIC_FIELDS))
        self.assertIn("snapshot_issues", SNAPSHOT_FIELDS)

    def test_numeric_snapshot_comparison(self):
        self.assertTrue(_same_value("trace_row_count", 5, 5.0))
        self.assertFalse(_same_value("trace_row_count", 5, 6))

    def test_removed_fields_are_absent_from_metadata(self):
        meta = frappe.get_meta("Mock Recall", cached=False)
        for fieldname in ("dispatched_qty", "attachments_note", "data_warning", "distribution_warning"):
            self.assertIsNone(meta.get_field(fieldname))
        self.assertTrue(meta.get_field("snapshot_issues").hidden)
