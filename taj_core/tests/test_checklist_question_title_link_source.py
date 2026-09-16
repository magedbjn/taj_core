import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUESTION_JSON = ROOT / "checklist" / "doctype" / "checklist_question" / "checklist_question.json"


class TestChecklistQuestionTitleLinkSource(unittest.TestCase):
    def test_question_is_used_as_link_title(self):
        meta = json.loads(QUESTION_JSON.read_text(encoding="utf-8"))

        self.assertEqual(meta.get("title_field"), "question")
        self.assertEqual(meta.get("show_title_field_in_link"), 1)


if __name__ == "__main__":
    unittest.main()
