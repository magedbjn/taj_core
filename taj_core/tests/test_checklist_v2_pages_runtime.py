from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


class TestChecklistV2PagesRuntime(TestCase):
    def test_today_data_groups_current_users_work(self):
        from taj_core.checklist import api as module

        today = module.nowdate()
        rows = [
            {
                "name": "A",
                "docstatus": 0,
                "status": "Draft",
                "posting_date": today,
                "assignment_type": "Any User in Department",
                "assigned_user": None,
                "answer_by": None,
                "taken_by": None,
                "result_status": "Normal",
                "has_issue": 0,
            },
            {
                "name": "B",
                "docstatus": 0,
                "status": "In Progress",
                "posting_date": today,
                "assignment_type": "Any User in Department",
                "assigned_user": None,
                "answer_by": None,
                "taken_by": "worker@example.com",
                "result_status": "Normal",
                "has_issue": 0,
            },
            {
                "name": "C",
                "docstatus": 1,
                "status": "Completed",
                "posting_date": today,
                "assignment_type": "Specific User",
                "assigned_user": "worker@example.com",
                "answer_by": "worker@example.com",
                "taken_by": "worker@example.com",
                "result_status": "Normal",
                "has_issue": 0,
            },
        ]

        with (
            patch.object(module.frappe, "session", SimpleNamespace(user="worker@example.com")),
            patch.object(module, "is_checklist_manager", return_value=False),
            patch.object(module, "_get_operational_docs", return_value=rows),
            patch.object(module, "_get_current_employee_identity", return_value={"employee": "EMP-1", "employee_name": "Worker", "department": "Production - Taj"}),
            patch.object(module, "_get_open_action_rows", return_value=[]),
            patch.object(module, "_get_checklist_settings", return_value={"enable_auto_save": 0}),
        ):
            data = module.get_checklist_today_data()

        self.assertEqual(data["is_manager"], 0)
        self.assertEqual(len(data["today"]), 3)
        self.assertEqual(data["summary"]["not_started"], 1)
        self.assertEqual(data["summary"]["in_progress"], 1)
        self.assertEqual(data["summary"]["completed"], 1)

    def test_control_room_summarizes_manager_view(self):
        from taj_core.checklist import api as module

        today = module.nowdate()
        rows = [
            {
                "name": "DONE",
                "docstatus": 1,
                "status": "Completed",
                "posting_date": today,
                "department": "QC - Taj",
                "result_status": "Normal",
                "has_issue": 0,
            },
            {
                "name": "LATE",
                "docstatus": 0,
                "status": "Expired",
                "posting_date": today,
                "department": "Warehouse - Taj",
                "delay_minutes": 45,
                "result_status": "Critical",
                "has_issue": 1,
            },
        ]

        with (
            patch.object(module, "_ensure_manager"),
            patch.object(module, "_get_operational_docs", return_value=rows),
        ):
            data = module.get_checklist_control_room_data()

        self.assertEqual(data["summary"]["completed"], 1)
        self.assertEqual(data["summary"]["overdue"], 1)
        self.assertEqual(data["summary"]["critical"], 1)
        self.assertEqual(data["summary"]["completion_percent"], 50.0)
        self.assertEqual(data["attention"][0]["name"], "LATE")


if __name__ == "__main__":
    import unittest
    unittest.main()
