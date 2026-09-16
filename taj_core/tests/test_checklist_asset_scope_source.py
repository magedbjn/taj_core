import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
TEMPLATE_JSON = CHECKLIST / "doctype" / "checklist_question_template" / "checklist_question_template.json"
ANSWER_JSON = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.json"
ACTION_JSON = CHECKLIST / "doctype" / "checklist_action" / "checklist_action.json"
ANSWER_CONTROLLER = CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py"
ACTIONS = CHECKLIST / "actions.py"
API = CHECKLIST / "api.py"
PRINT_FORMAT = CHECKLIST / "print_format" / "checklist_log_1" / "checklist_log_1.json"


class TestChecklistAssetScopeSource(unittest.TestCase):
    def _fields(self, path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {row["fieldname"]: row for row in doc["fields"] if row.get("fieldname")}

    def test_template_answer_and_action_have_asset_links(self):
        template = self._fields(TEMPLATE_JSON)
        answer = self._fields(ANSWER_JSON)
        action = self._fields(ACTION_JSON)
        for fields in (template, answer, action):
            self.assertIn("asset", fields)
            self.assertEqual(fields["asset"].get("fieldtype"), "Link")
            self.assertEqual(fields["asset"].get("options"), "Asset")
        self.assertEqual(answer["asset"].get("read_only"), 1)
        self.assertEqual(action["asset"].get("read_only"), 1)

    def test_official_checklist_print_includes_asset_when_present(self):
        source = PRINT_FORMAT.read_text(encoding="utf-8")
        self.assertIn("doc.asset", source)
        self.assertIn("Asset", source)

    def test_asset_flows_from_template_to_answer_and_action_identity(self):
        controller = ANSWER_CONTROLLER.read_text(encoding="utf-8")
        actions = ACTIONS.read_text(encoding="utf-8")
        api = API.read_text(encoding="utf-8")
        self.assertIn('"asset"', controller)
        self.assertIn('self.asset = getattr(template, "asset", None)', controller)
        self.assertIn('getattr(doc, "asset", None)', actions)
        self.assertIn('action.asset = getattr(doc, "asset", None)', actions)
        self.assertIn('"asset": getattr(doc, "asset", None)', api)


if __name__ == "__main__":
    unittest.main()
