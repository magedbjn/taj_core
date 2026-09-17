import json
import unittest
from pathlib import Path

from taj_core.checklist.gmp_catalog import GMP_QUESTIONS

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
ANSWER_PY = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py"
USER_JS = CHECKLIST / "page" / "checklist_user" / "checklist_user.js"
ACTIONS_PY = CHECKLIST / "actions.py"
QUESTION_JSON = CHECKLIST / "doctype" / "checklist_question" / "checklist_question.json"


class TestChecklistOptionalEvidenceSource(unittest.TestCase):
    def test_gmp_catalog_never_requires_failure_photo(self):
        for key, question in GMP_QUESTIONS.items():
            self.assertEqual(question.get("require_failure_photo"), 0, key)
            self.assertEqual(question.get("allow_no_photo_with_reason"), 0, key)

    def test_required_photo_configuration_is_hidden_from_question_setup(self):
        data = json.loads(QUESTION_JSON.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in data["fields"] if row.get("fieldname")}
        self.assertEqual(fields["require_failure_photo"].get("hidden"), 1)
        self.assertEqual(fields["allow_no_photo_with_reason"].get("hidden"), 1)

    def test_server_failure_validation_does_not_require_photo(self):
        source = ANSWER_PY.read_text(encoding="utf-8")
        start = source.index("def validate_failure_details")
        end = source.index("def validate_answer_value", start)
        block = source[start:end]
        self.assertNotIn("require_failure_photo", block)
        self.assertNotIn("failure_photo_requirement_satisfied", block)
        self.assertNotIn("requires a photo", block)

    def test_user_page_always_offers_optional_photo_and_never_blocks_submit_for_it(self):
        source = USER_JS.read_text(encoding="utf-8")

        render_start = source.index("    render_failure_photo(row, $panel) {")
        render_end = source.index("    render_worker_section()", render_start)
        render_block = source[render_start:render_end]
        self.assertNotIn("if (!Number(row.require_failure_photo", render_block)
        self.assertIn('__("Photo (Optional)")', render_block)
        self.assertNotIn('__("No Photo Available Reason")', render_block)

        validate_start = source.index("    validate_before_submit() {")
        validate_end = source.index("    async submit_doc()", validate_start)
        validate_block = source[validate_start:validate_end]
        self.assertNotIn("require_failure_photo", validate_block)
        self.assertNotIn("photo is required", validate_block)
        self.assertNotIn("photo or no-photo reason is required", validate_block)

    def test_action_latest_issue_note_prefers_user_note_with_system_fallback(self):
        source = ACTIONS_PY.read_text(encoding="utf-8")
        self.assertIn("def _latest_issue_note(row):", source)
        self.assertIn('getattr(row, "user_note", None)', source)
        self.assertIn('getattr(row, "issue_note", None)', source)
        self.assertGreaterEqual(source.count("action.latest_issue_note = _latest_issue_note(row)"), 2)


if __name__ == "__main__":
    unittest.main()
