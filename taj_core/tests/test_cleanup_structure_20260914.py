from pathlib import Path
import csv
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestCleanupStructure20260914(unittest.TestCase):
    def test_obsolete_orphan_files_are_removed(self):
        obsolete = [
            ROOT / "utils" / "jc_board_realtime.py",
            ROOT / "utils" / "salary_calculation.py",
            ROOT / "patches" / "fix_manufacturing_on_hold.sp",
        ]
        self.assertEqual([str(path.relative_to(ROOT)) for path in obsolete if path.exists()], [])

    def test_catering_shared_helpers_are_centralized(self):
        shared = ROOT / "catering" / "utils.py"
        self.assertTrue(shared.exists())

        capacity = (ROOT / "catering" / "doctype" / "catering_capacity" / "catering_capacity.py").read_text()
        requirement = (
            ROOT / "catering" / "doctype" / "catering_buffet_requirement" / "catering_buffet_requirement.py"
        ).read_text()

        self.assertIn("from taj_core.catering.utils import get_capacity_key, get_item_display_names", capacity)
        self.assertIn("from taj_core.catering.utils import get_capacity_key, get_item_display_names", requirement)
        self.assertNotIn("def get_capacity_key(", capacity)
        self.assertNotIn("def get_capacity_key(", requirement)
        self.assertNotIn("def get_item_display_names(", capacity)
        self.assertNotIn("def get_item_display_names(", requirement)

    def test_manufacturing_shared_helpers_are_centralized(self):
        shared = ROOT / "taj_manufacturing" / "production_plan_helpers.py"
        self.assertTrue(shared.exists())

        board = (ROOT / "taj_core" / "page" / "job_card_board" / "job_card_board.py").read_text()
        labels = (ROOT / "taj_manufacturing" / "api" / "preparation_labels.py").read_text()

        for source in (board, labels):
            self.assertIn("taj_core.taj_manufacturing.production_plan_helpers", source)
            self.assertNotIn("def _existing_fields(", source)
            self.assertNotIn("def _resolve_pp_item_reference(", source)
            self.assertNotIn("def _get_sub_assembly_row_fields(", source)

    def test_stale_commented_purchase_order_implementation_is_removed(self):
        source = (ROOT / "custom" / "production_plan.py").read_text()
        self.assertNotIn("make_purchase_order_from_production_plan", source)

    def test_translation_csv_rows_are_well_formed(self):
        path = ROOT / "translations" / "ar.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        malformed = [(index, row) for index, row in enumerate(rows, 1) if len(row) not in (2, 3)]
        self.assertEqual(malformed, [])
        translations = {row[0]: row[1] for row in rows if len(row) >= 2}
        self.assertEqual(
            translations.get("Default Required Worker Count (Optional)"),
            "العدد الافتراضي المطلوب من العمال (اختياري)",
        )

    def test_translation_csv_has_no_exact_duplicate_rows(self):
        path = ROOT / "translations" / "ar.csv"
        seen = set()
        duplicates = []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.reader(handle), 1):
                key = (row[0], row[1], row[2] if len(row) > 2 else "")
                if key in seen:
                    duplicates.append((index, key))
                seen.add(key)
        self.assertEqual(duplicates, [])

    def test_package_init_has_no_unnecessary_frappe_import(self):
        source = (ROOT / "__init__.py").read_text()
        self.assertNotIn("import frappe", source)
        self.assertIn("__version__", source)


if __name__ == "__main__":
    unittest.main()
