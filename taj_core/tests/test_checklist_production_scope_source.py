from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "checklist" / "production.py"


class TestChecklistProductionScopeSource(unittest.TestCase):
    def test_production_readiness_resolves_work_order_company(self):
        source = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn('frappe.db.get_value("Work Order", work_order_name, "company")', source)
        self.assertIn("work_order_company", source)

    def test_schedule_query_is_scoped_to_work_order_company(self):
        source = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn('"company": work_order_company', source)

    def test_legacy_template_fallback_skips_other_company_departments(self):
        source = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn("template_department_company", source)
        self.assertIn("template_department_company != work_order_company", source)

    def test_legacy_fallback_only_applies_to_templates_with_no_schedule_anywhere(self):
        source = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn("all_scheduled_templates", source)
        self.assertIn("if template_name in all_scheduled_templates", source)


if __name__ == "__main__":
    unittest.main()
