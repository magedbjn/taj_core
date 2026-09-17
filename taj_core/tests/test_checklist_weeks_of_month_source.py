import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"


class TestChecklistWeeksOfMonthSource(unittest.TestCase):
    def test_schedule_schema_exposes_visual_week_selection(self):
        path = CHECKLIST / "doctype" / "checklist_schedule" / "checklist_schedule.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in data["fields"]}

        self.assertIn("Weeks of Month", fields["schedule_type"]["options"].splitlines())
        for week in range(1, 6):
            field = fields[f"week_{week}"]
            self.assertEqual(field["fieldtype"], "Check")
            self.assertIn("Weeks of Month", field.get("depends_on", ""))
        self.assertIn("Weeks of Month", fields["day_of_week"].get("depends_on", ""))

    def test_schedule_validation_uses_week_pattern_helper(self):
        path = CHECKLIST / "doctype" / "checklist_schedule" / "checklist_schedule.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("normalize_schedule_weeks", source)
        self.assertIn('schedule_type == "Weeks of Month"', source)
        self.assertIn("Select at least one week of month", source)

    def test_due_date_calculation_uses_schedule_week_pattern_helper(self):
        path = CHECKLIST / "rules.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("def calculate_schedule_due_date", source)
        self.assertIn("normalize_schedule_weeks(schedule)", source)
        self.assertIn('schedule_type == "Weeks of Month"', source)


if __name__ == "__main__":
    unittest.main()
