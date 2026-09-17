from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "checklist" / "rules.py"


class TestChecklistWeeksOfMonth(unittest.TestCase):
    def _rules(self):
        namespace = {}
        exec(RULES_PATH.read_text(encoding="utf-8"), namespace)
        return namespace

    def test_parse_weeks_accepts_trimmed_unique_values(self):
        parse = self._rules()["parse_weeks_of_month"]
        self.assertEqual(parse("1, 3"), [1, 3])
        self.assertEqual(parse("5,2,4"), [2, 4, 5])

    def test_parse_weeks_rejects_duplicates_and_out_of_range_values(self):
        parse = self._rules()["parse_weeks_of_month"]
        with self.assertRaises(ValueError):
            parse("1,1")
        with self.assertRaises(ValueError):
            parse("0,3")
        with self.assertRaises(ValueError):
            parse("1,6")
        with self.assertRaises(ValueError):
            parse("")

    def test_next_due_date_moves_to_next_selected_week_on_same_weekday(self):
        next_due = self._rules()["next_week_of_month_due_date"]
        # 2026-09-07 is Monday in days 1-7 (week 1).
        self.assertEqual(next_due(date(2026, 9, 7), [1, 3]), date(2026, 9, 21))

    def test_next_due_date_crosses_month_without_fourteen_day_drift(self):
        next_due = self._rules()["next_week_of_month_due_date"]
        # Monday in September week 3 -> first Monday in October week 1.
        self.assertEqual(next_due(date(2026, 9, 21), [1, 3]), date(2026, 10, 5))
        # Monday in a week-4 cycle -> Monday in next month's week 2.
        self.assertEqual(next_due(date(2026, 9, 28), [2, 4]), date(2026, 10, 12))

    def test_week_five_is_skipped_when_month_has_no_matching_weekday(self):
        next_due = self._rules()["next_week_of_month_due_date"]
        # Monday 2026-08-31 is week 5. September and October have no Monday
        # in days 29-31, so a week-5-only pattern advances to 2026-11-30.
        self.assertEqual(next_due(date(2026, 8, 31), [5]), date(2026, 11, 30))


if __name__ == "__main__":
    unittest.main()
