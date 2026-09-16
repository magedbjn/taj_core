import ast
from collections import defaultdict
from pathlib import Path
import unittest

API_PATH = Path(__file__).resolve().parents[1] / "checklist" / "api.py"
SOURCE = API_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def load_functions(*names):
    selected = []
    wanted = set(names)
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            selected.append(node)
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "defaultdict": defaultdict,
        "OPEN_STATUSES": ("Draft", "In Progress", "Expired"),
        "cstr": lambda value: "" if value is None else str(value),
        "flt": lambda value: float(value or 0),
        "_": lambda value: value,
    }
    exec(compile(module, str(API_PATH), "exec"), namespace)
    return namespace


class TestChecklistV2AggregationSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions(
            "_operational_bucket",
            "_is_operational_for_date",
            "_build_operational_summary",
            "_build_department_health",
            "_build_team_summary",
            "_build_attention_rows",
        )


    def test_future_open_task_is_not_in_current_operational_view(self):
        helper = self.ns["_is_operational_for_date"]
        self.assertTrue(helper({"docstatus": 0, "posting_date": "2026-09-13"}, "2026-09-14"))
        self.assertTrue(helper({"docstatus": 0, "posting_date": "2026-09-14"}, "2026-09-14"))
        self.assertFalse(helper({"docstatus": 0, "posting_date": "2026-09-15"}, "2026-09-14"))
        self.assertTrue(helper({"docstatus": 1, "posting_date": "2026-09-14"}, "2026-09-14"))
        self.assertFalse(helper({"docstatus": 1, "posting_date": "2026-09-13"}, "2026-09-14"))

    def test_operational_summary_separates_overdue_progress_and_completed(self):
        rows = [
            {"name": "A", "docstatus": 0, "status": "Draft", "time_status": "", "delay_minutes": 0},
            {"name": "B", "docstatus": 0, "status": "In Progress", "time_status": "", "delay_minutes": 0},
            {"name": "C", "docstatus": 0, "status": "Expired", "time_status": "Overdue", "delay_minutes": 20, "has_issue": 1, "result_status": "Critical"},
            {"name": "D", "docstatus": 1, "status": "Completed", "has_issue": 0, "result_status": "Normal"},
        ]
        summary = self.ns["_build_operational_summary"](rows)
        self.assertEqual(summary["not_started"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["overdue"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["critical"], 1)

    def test_department_health_prioritizes_critical_and_overdue_departments(self):
        rows = [
            {"department": "QC - Taj", "docstatus": 0, "status": "Expired", "delay_minutes": 30, "has_issue": 1, "result_status": "Critical"},
            {"department": "Warehouse - Taj", "docstatus": 1, "status": "Completed", "has_issue": 0, "result_status": "Normal"},
        ]
        health = self.ns["_build_department_health"](rows)
        self.assertEqual(health[0]["department"], "QC - Taj")
        self.assertEqual(health[0]["health"], "critical")
        self.assertEqual(health[1]["health"], "good")

    def test_attention_rows_put_production_start_exception_first(self):
        rows = [
            {"name": "LATE", "docstatus": 0, "status": "Expired", "delay_minutes": 90, "has_issue": 0, "result_status": "Normal"},
            {"name": "EARLY", "docstatus": 0, "status": "Draft", "delay_minutes": 0, "has_issue": 0, "result_status": "Normal", "production_started_before_completion": 1},
        ]
        attention = self.ns["_build_attention_rows"](rows)
        self.assertEqual(attention[0]["name"], "EARLY")
        self.assertEqual(attention[0]["attention_level"], "critical")
        self.assertEqual(attention[1]["name"], "LATE")


if __name__ == "__main__":
    unittest.main()
