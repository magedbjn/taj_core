import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"


class TestChecklistGmpMetadataSource(unittest.TestCase):
    def _fields(self, *parts):
        data = json.loads((CHECKLIST.joinpath(*parts)).read_text(encoding="utf-8"))
        return {field["fieldname"]: field for field in data["fields"]}, data

    def test_question_schema_has_group_and_structured_standards_table(self):
        fields, data = self._fields("doctype", "checklist_question", "checklist_question.json")
        self.assertIn("question_group", fields)
        self.assertEqual(fields["question_group"]["fieldtype"], "Data")
        self.assertFalse(bool(fields["question_group"].get("reqd")))
        self.assertIn("standards", fields)
        self.assertEqual(fields["standards"]["fieldtype"], "Table")
        self.assertEqual(fields["standards"]["options"], "Checklist Question Standard")
        self.assertIn("standard_reference", fields)
        self.assertEqual(fields["standard_reference"]["fieldtype"], "Small Text")
        self.assertEqual(fields["standard_reference"].get("hidden"), 1)
        self.assertEqual(fields["standard_reference"].get("read_only"), 1)
        self.assertIn("question_group", data["field_order"])
        self.assertIn("standards", data["field_order"])
        self.assertIn("standard_reference", data["field_order"])

    def test_standard_master_and_question_standard_child_schema_exist(self):
        standard_fields, standard_data = self._fields("doctype", "checklist_standard", "checklist_standard.json")
        self.assertEqual(standard_data["autoname"], "field:standard_name")
        self.assertEqual(standard_fields["standard_name"]["fieldtype"], "Data")
        self.assertEqual(standard_fields["standard_name"].get("unique"), 1)
        self.assertEqual(standard_fields["active"].get("default"), "1")

        row_fields, row_data = self._fields(
            "doctype", "checklist_question_standard", "checklist_question_standard.json"
        )
        self.assertEqual(row_data.get("istable"), 1)
        self.assertEqual(row_fields["standard"]["fieldtype"], "Link")
        self.assertEqual(row_fields["standard"]["options"], "Checklist Standard")
        self.assertEqual(row_fields["reference"]["fieldtype"], "Data")

    def test_answer_question_schema_has_read_only_snapshots(self):
        fields, data = self._fields("doctype", "checklist_answer_question", "checklist_answer_question.json")
        for fieldname in ("question_group", "standard_reference"):
            self.assertIn(fieldname, fields)
            self.assertEqual(fields[fieldname].get("read_only"), 1)
            self.assertEqual(fields[fieldname].get("hidden"), 1)
            self.assertIn(fieldname, data["field_order"])

    def test_answer_builder_snapshots_metadata(self):
        source = (CHECKLIST / "doctype" / "checklist_answer" / "checklist_answer.py").read_text(encoding="utf-8")
        start = source.index("snapshot_fields = (")
        end = source.index(")", start)
        snapshot_block = source[start:end]
        self.assertIn('"question_group"', snapshot_block)
        self.assertIn('"standard_reference"', snapshot_block)

    def test_api_serializes_group_and_reference(self):
        source = (CHECKLIST / "api.py").read_text(encoding="utf-8")
        start = source.index("def serialize_checklist_answer")
        block = source[start:]
        self.assertIn('"question_group"', block)
        self.assertIn('"standard_reference"', block)


if __name__ == "__main__":
    unittest.main()
