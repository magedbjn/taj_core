import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
ACTION_JSON = CHECKLIST / "doctype" / "checklist_action" / "checklist_action.json"
OCCURRENCE_JSON = CHECKLIST / "doctype" / "checklist_action_occurrence" / "checklist_action_occurrence.json"
ANSWER_ROW_JSON = CHECKLIST / "doctype" / "checklist_answer_question" / "checklist_answer_question.json"


class TestChecklistActionSchemaSource(unittest.TestCase):
    def test_action_doctype_exists_with_required_control_fields(self):
        self.assertTrue(ACTION_JSON.exists(), "Checklist Action DocType JSON is required")
        doc = json.loads(ACTION_JSON.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in doc["fields"] if row.get("fieldname")}
        for fieldname in (
            "status", "issue_key", "open_issue_key", "source_checklist", "latest_checklist",
            "source_template", "question", "question_text", "department", "plant_floor", "warehouse", "asset",
            "severity", "quality_impact", "responsible_department", "responsible_user", "due_at",
            "requires_verification", "latest_observation", "latest_answer", "occurrence_count",
            "first_detected_at", "last_detected_at", "resolution_details", "resolution_photo",
            "resolved_by", "resolved_at", "verification_user", "verification_department",
            "verification_note", "verified_by", "verified_at", "waiting_reason", "occurrences",
            "material_request", "asset_repair",
        ):
            self.assertIn(fieldname, fields)
        self.assertEqual(fields["status"].get("options"), "Open\nIn Progress\nWaiting\nPending Verification\nClosed")
        self.assertEqual(fields["open_issue_key"].get("unique"), 1)
        self.assertEqual(fields["occurrences"].get("options"), "Checklist Action Occurrence")

    def test_actions_are_system_generated_and_not_manually_created_or_deleted(self):
        doc = json.loads(ACTION_JSON.read_text(encoding="utf-8"))
        for permission in doc.get("permissions", []):
            self.assertNotEqual(permission.get("create"), 1)
            self.assertNotEqual(permission.get("delete"), 1)

    def test_occurrence_doctype_preserves_issue_and_pass_observations(self):
        self.assertTrue(OCCURRENCE_JSON.exists(), "Checklist Action Occurrence child DocType is required")
        doc = json.loads(OCCURRENCE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(doc.get("istable"), 1)
        fields = {row["fieldname"]: row for row in doc["fields"] if row.get("fieldname")}
        for fieldname in (
            "observation_type", "checklist_answer", "checklist_row_id", "posting_date", "observed_at",
            "answer", "issue_note", "failure_reason", "user_note", "evidence_photo", "severity",
            "quality_impact", "observer",
        ):
            self.assertIn(fieldname, fields)
        self.assertEqual(fields["observation_type"].get("options"), "Issue\nPass Observation")

    def test_answer_row_links_to_action_without_taj_prefix(self):
        doc = json.loads(ANSWER_ROW_JSON.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in doc["fields"] if row.get("fieldname")}
        self.assertIn("checklist_action", fields)
        self.assertEqual(fields["checklist_action"].get("options"), "Checklist Action")
        self.assertEqual(fields["checklist_action"].get("read_only"), 1)


if __name__ == "__main__":
    unittest.main()
