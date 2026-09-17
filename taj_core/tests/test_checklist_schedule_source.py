import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
HOOKS = ROOT / "hooks.py"


class TestChecklistScheduleSource(unittest.TestCase):
    def test_schedule_schema_exposes_supported_recurrence_and_read_only_next_due(self):
        path = CHECKLIST / "doctype" / "checklist_schedule" / "checklist_schedule.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in data["fields"]}

        self.assertEqual(
            fields["schedule_type"]["options"].splitlines(),
            ["Manual", "Daily", "Weekly", "Monthly", "Weeks of Month", "Quarterly", "Yearly"],
        )
        self.assertEqual(fields["next_due_date"].get("read_only"), 1)
        self.assertEqual(fields["company"].get("options"), "Company")
        self.assertEqual(fields["department"].get("options"), "Department")

    def test_schedule_controller_owns_recurrence_and_manual_creation(self):
        path = CHECKLIST / "doctype" / "checklist_schedule" / "checklist_schedule.py"
        source = path.read_text(encoding="utf-8")

        self.assertIn("calculate_schedule_due_date", source)
        self.assertIn("normalize_schedule_weeks", source)
        self.assertIn("def create_checklist(schedule_name):", source)
        self.assertIn('if schedule.schedule_type != "Manual"', source)
        self.assertIn('schedule.check_permission("read")', source)

    def test_scheduler_and_migration_hooks_point_to_schedule_architecture(self):
        hooks_source = HOOKS.read_text(encoding="utf-8")
        self.assertIn("taj_core.checklist.scheduler.daily_checklist_scheduler", hooks_source)
        self.assertIn('before_migrate = "taj_core.checklist.schedule_migration.before_migrate"', hooks_source)
        self.assertIn('after_migrate = "taj_core.checklist.schedule_migration.after_migrate"', hooks_source)

        migration = (CHECKLIST / "schedule_migration.py").read_text(encoding="utf-8")
        self.assertIn("def _deduplicate_generation_keys():", migration)
        self.assertIn("def sync_legacy_template_schedules():", migration)


if __name__ == "__main__":
    unittest.main()
