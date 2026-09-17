from datetime import date
from types import SimpleNamespace
import unittest

from taj_core.checklist.rules import schedule_due_occurrences


class TestChecklistScheduleCatchup(unittest.TestCase):
    def test_daily_schedule_returns_every_overdue_cycle_through_today(self):
        schedule = SimpleNamespace(schedule_type="Daily", interval=1, start_date=date(2026, 9, 1))
        result = schedule_due_occurrences(
            schedule,
            next_due_date=date(2026, 9, 1),
            through_date=date(2026, 9, 10),
        )
        self.assertEqual(result, [date(2026, 9, day) for day in range(1, 11)])

    def test_no_occurrences_when_next_due_is_in_future(self):
        schedule = SimpleNamespace(schedule_type="Daily", interval=1, start_date=date(2026, 9, 20))
        self.assertEqual(
            schedule_due_occurrences(schedule, date(2026, 9, 20), date(2026, 9, 10)),
            [],
        )

    def test_safety_cap_processes_a_bounded_batch_and_can_continue_later(self):
        schedule = SimpleNamespace(schedule_type="Daily", interval=1, start_date=date(2026, 1, 1))
        self.assertEqual(
            schedule_due_occurrences(
                schedule,
                next_due_date=date(2026, 1, 1),
                through_date=date(2026, 1, 10),
                max_cycles=3,
            ),
            [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
        )


if __name__ == "__main__":
    unittest.main()
