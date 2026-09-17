from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"


class TestChecklistQuestionGroupsSource(unittest.TestCase):
    def test_user_page_renders_group_headings_without_standard_reference_badge(self):
        js = (CHECKLIST / "page" / "checklist_user" / "checklist_user.js").read_text(encoding="utf-8")
        css = (CHECKLIST / "page" / "checklist_user" / "checklist_user.css").read_text(encoding="utf-8")
        self.assertIn("render_question_group_heading", js)
        self.assertIn("question_group", js)
        self.assertNotIn("question-reference-badge", js)
        self.assertIn("checklist-question-group-heading", js)
        self.assertIn(".checklist-question-group-heading", css)

    def test_admin_drawer_renders_group_headings_without_standard_reference_badge(self):
        js = (CHECKLIST / "page" / "checklist_admin" / "checklist_admin.js").read_text(encoding="utf-8")
        css = (CHECKLIST / "page" / "checklist_admin" / "checklist_admin.css").read_text(encoding="utf-8")
        self.assertIn("render_question_group_heading", js)
        self.assertIn("question_group", js)
        self.assertNotIn("question-reference-badge", js)
        self.assertIn("checklist-question-group-heading", js)
        self.assertIn(".checklist-question-group-heading", css)


if __name__ == "__main__":
    unittest.main()
