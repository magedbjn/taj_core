from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPAIR = ROOT / "checklist" / "engineering_maintenance_repairs.py"


class TestEngineeringMaintenanceRepairsSource(unittest.TestCase):
    def test_non_destructive_review_repair_command_exists(self):
        self.assertTrue(REPAIR.exists())
        source = REPAIR.read_text(encoding="utf-8")
        self.assertIn("apply_reviewed_template_repairs", source)
        self.assertIn("REVIEWED_TEMPLATE_REPAIRS", source)
        self.assertNotIn("delete_doc", source)
        self.assertNotIn("periodicity", source)
        self.assertNotIn("schedule_time", source)


if __name__ == "__main__":
    unittest.main()
