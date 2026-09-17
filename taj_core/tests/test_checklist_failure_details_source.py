import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
QUESTION_JSON = CHECKLIST / "doctype" / "checklist_question" / "checklist_question.json"
ANSWER_ROW_JSON = CHECKLIST / "doctype" / "checklist_answer_question" / "checklist_answer_question.json"
ACTION_JSON = CHECKLIST / "doctype" / "checklist_action" / "checklist_action.json"
OCCURRENCE_JSON = CHECKLIST / "doctype" / "checklist_action_occurrence" / "checklist_action_occurrence.json"
ANSWER_PY = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py"
API_PY = CHECKLIST / "api.py"
ACTIONS_PY = CHECKLIST / "actions.py"
USER_JS = CHECKLIST / "page" / "checklist_user" / "checklist_user.js"
ADMIN_JS = CHECKLIST / "page" / "checklist_admin" / "checklist_admin.js"


def fields(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {row["fieldname"]: row for row in doc["fields"] if row.get("fieldname")}


class TestChecklistFailureDetailsSource(unittest.TestCase):
    def test_question_can_configure_affected_item_and_issue_type(self):
        question_fields = fields(QUESTION_JSON)
        for fieldname in (
            "require_affected_item",
            "affected_item_options",
            "require_issue_type",
            "issue_type_options",
        ):
            self.assertIn(fieldname, question_fields)
        self.assertEqual(question_fields["affected_item_options"]["fieldtype"], "Small Text")
        self.assertEqual(question_fields["issue_type_options"]["fieldtype"], "Small Text")

    def test_answer_row_snapshots_config_and_records_failure_scope(self):
        answer_fields = fields(ANSWER_ROW_JSON)
        for fieldname in (
            "require_affected_item",
            "affected_item_options",
            "affected_items",
            "require_issue_type",
            "issue_type_options",
            "issue_type",
        ):
            self.assertIn(fieldname, answer_fields)
        self.assertEqual(answer_fields["affected_items"]["fieldtype"], "Small Text")
        self.assertEqual(answer_fields["issue_type"]["fieldtype"], "Data")

    def test_action_and_occurrence_keep_structured_failure_scope(self):
        action_fields = fields(ACTION_JSON)
        for fieldname in ("action_title", "latest_affected_items", "latest_issue_type"):
            self.assertIn(fieldname, action_fields)
        self.assertEqual(json.loads(ACTION_JSON.read_text(encoding="utf-8")).get("title_field"), "question_text")

        occurrence_fields = fields(OCCURRENCE_JSON)
        self.assertIn("affected_items", occurrence_fields)
        self.assertIn("issue_type", occurrence_fields)

    def test_server_snapshots_saves_validates_and_clears_new_fields(self):
        answer_source = ANSWER_PY.read_text(encoding="utf-8")
        api_source = API_PY.read_text(encoding="utf-8")
        for token in (
            '"require_affected_item"',
            '"affected_item_options"',
            '"require_issue_type"',
            '"issue_type_options"',
            'row.affected_items = ""',
            'row.issue_type = ""',
            "requires an affected item",
            "has an invalid affected item",
            "requires an issue type",
            "has an invalid issue type",
        ):
            self.assertIn(token, answer_source)
        self.assertIn('"affected_items"', api_source)
        self.assertIn('"issue_type"', api_source)

    def test_actions_scope_identity_and_history_by_affected_item_and_issue_type(self):
        source = ACTIONS_PY.read_text(encoding="utf-8")
        self.assertIn('affected_items=getattr(row, "affected_items", None)', source)
        self.assertIn('issue_type=getattr(row, "issue_type", None)', source)
        self.assertIn('"affected_items": getattr(row, "affected_items", None)', source)
        self.assertIn('"issue_type": getattr(row, "issue_type", None)', source)
        self.assertIn("build_action_title", source)

    def test_pass_observation_can_reach_all_open_scoped_actions_for_the_broad_question(self):
        source = ACTIONS_PY.read_text(encoding="utf-8")
        self.assertIn("def _find_open_actions_for_question", source)
        self.assertIn("for action_name in _find_open_actions_for_question(doc, row)", source)
        self.assertIn('effect = "append_pass"', source)

    def test_user_ui_collects_multiselect_affected_items_and_single_issue_type(self):
        source = USER_JS.read_text(encoding="utf-8")
        for token in (
            "render_failure_affected_items",
            "render_failure_issue_type",
            "Affected Item",
            "Issue Type",
            "affected_items",
            "issue_type",
            "affected item is required",
            "issue type is required",
        ):
            self.assertIn(token, source)

    def test_readonly_views_show_failure_scope(self):
        user_source = USER_JS.read_text(encoding="utf-8")
        admin_source = ADMIN_JS.read_text(encoding="utf-8")
        for source in (user_source, admin_source):
            self.assertIn("Affected Item", source)
            self.assertIn("Issue Type", source)


if __name__ == "__main__":
    unittest.main()
