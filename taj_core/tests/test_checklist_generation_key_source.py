import json
from pathlib import Path
import unittest

from taj_core.checklist.rules import stable_generation_key

ROOT = Path(__file__).resolve().parents[1]
ANSWER_JSON = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.json"
ANSWER_PY = ROOT / "checklist" / "doctype" / "checklist_answer" / "checklist_answer.py"


class TestChecklistGenerationKeySource(unittest.TestCase):
    def test_generation_key_is_fixed_length_and_deterministic(self):
        long_schedule = "Schedule-" + ("X" * 300)
        first = stable_generation_key("GMP - Receiving", "2026-09-17", schedule_name=long_schedule)
        second = stable_generation_key("GMP - Receiving", "2026-09-17", schedule_name=long_schedule)
        other = stable_generation_key("GMP - Receiving", "2026-09-18", schedule_name=long_schedule)

        self.assertEqual(len(first), 64)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_generation_key_is_database_unique(self):
        data = json.loads(ANSWER_JSON.read_text(encoding="utf-8"))
        fields = {row.get("fieldname"): row for row in data["fields"]}
        self.assertEqual(fields["generation_key"].get("unique"), 1)

    def test_generated_insert_recovers_duplicate_race_by_generation_key(self):
        source = ANSWER_PY.read_text(encoding="utf-8")
        self.assertIn("def _insert_generated_answer", source)
        self.assertIn('frappe.db.exists("Checklist Answer", {"generation_key": doc.generation_key})', source)
        self.assertIn('existing_doc.flags.reuse_reason = "generation_key_race"', source)

    def test_before_migrate_clears_duplicate_generation_keys_before_unique_index(self):
        migration = (ROOT / "checklist" / "schedule_migration.py").read_text(encoding="utf-8")
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("def before_migrate", migration)
        self.assertIn("_normalize_generation_keys", migration)
        self.assertIn("_deduplicate_generation_keys", migration)
        self.assertIn("set generation_key = null", migration.lower())
        self.assertIn('before_migrate = "taj_core.checklist.schedule_migration.before_migrate"', hooks)


if __name__ == "__main__":
    unittest.main()
