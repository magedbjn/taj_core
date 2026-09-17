from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "checklist" / "doctype" / "checklist_schedule" / "checklist_schedule.py"


class TestChecklistScheduleScopeSource(unittest.TestCase):
    def test_schedule_validates_company_scope(self):
        source = SCHEDULE.read_text(encoding="utf-8")
        self.assertIn("self._validate_company_scope()", source)
        self.assertIn("def _validate_company_scope", source)
        self.assertIn('frappe.db.get_value("Department", self.department, "company")', source)
        self.assertIn("does not belong to Company", source)

    def test_optional_scope_links_are_checked_when_they_expose_company(self):
        source = SCHEDULE.read_text(encoding="utf-8")
        self.assertIn('("plant_floor", "Plant Floor")', source)
        self.assertIn('("warehouse", "Warehouse")', source)
        self.assertIn('("asset", "Asset")', source)
        self.assertIn('frappe.get_meta(doctype).has_field("company")', source)


if __name__ == "__main__":
    unittest.main()
