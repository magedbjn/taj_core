import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANSWER_JSON = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.json"
ANSWER_PY = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.py"


class TestChecklistAnswerScheduleIdentitySource(unittest.TestCase):
    def test_template_and_department_are_read_only_snapshots(self):
        data = json.loads(ANSWER_JSON.read_text(encoding="utf-8"))
        fields = {row.get("fieldname"): row for row in data["fields"]}
        self.assertEqual(fields["template"].get("read_only"), 1)
        self.assertEqual(fields["department"].get("read_only"), 1)

    def test_validation_checks_schedule_identity(self):
        source = ANSWER_PY.read_text(encoding="utf-8")
        self.assertIn("self.validate_schedule_identity()", source)
        self.assertIn("def validate_schedule_identity", source)
        self.assertIn('"Checklist Schedule"', source)
        self.assertIn("does not match its Checklist Schedule", source)


if __name__ == "__main__":
    unittest.main()
