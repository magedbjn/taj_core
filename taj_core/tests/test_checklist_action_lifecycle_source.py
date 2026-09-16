from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"
ACTION_PY = CHECKLIST / "doctype" / "checklist_action" / "checklist_action.py"
NOTIFY_PY = CHECKLIST / "action_notifications.py"
PERMISSIONS_PY = CHECKLIST / "permissions.py"
HOOKS_PY = ROOT / "hooks.py"


class TestChecklistActionLifecycleSource(unittest.TestCase):
    def test_action_requires_documented_resolution_and_verification(self):
        source = ACTION_PY.read_text(encoding="utf-8")
        self.assertIn("def validate", source)
        self.assertIn("resolution_details", source)
        self.assertIn("Pending Verification", source)
        self.assertIn("verified_by", source)
        self.assertIn("open_issue_key", source)
        self.assertIn("def submit_resolution", source)
        self.assertIn("next_resolution_status", source)
        self.assertIn("def verify_resolution", source)
        self.assertIn("In Progress", source)
        self.assertIn("def set_waiting", source)
        self.assertIn("waiting_reason", source)

    def test_action_permissions_are_scoped_to_responsible_and_verification_owners(self):
        source = PERMISSIONS_PY.read_text(encoding="utf-8")
        self.assertIn("def checklist_action_has_permission", source)
        self.assertIn("def checklist_action_query_conditions", source)
        self.assertIn("responsible_user", source)
        self.assertIn("responsible_department", source)
        self.assertIn("verification_user", source)
        self.assertIn("verification_department", source)
        hooks = HOOKS_PY.read_text(encoding="utf-8")
        self.assertIn('"Checklist Action": "taj_core.checklist.permissions.checklist_action_query_conditions"', hooks)
        self.assertIn('"Checklist Action": "taj_core.checklist.permissions.checklist_action_has_permission"', hooks)

    def test_action_permission_hook_blocks_manual_create_and_delete_even_for_managers(self):
        source = PERMISSIONS_PY.read_text(encoding="utf-8")
        guard = 'if permission_type in ("create", "delete"):'
        self.assertIn(guard, source)
        self.assertLess(source.index(guard), source.index("if is_checklist_manager(user):", source.index("def checklist_action_has_permission")))

    def test_action_notifications_exist_for_creation_and_verification(self):
        self.assertTrue(NOTIFY_PY.exists(), "Checklist Action notifications are required")
        source = NOTIFY_PY.read_text(encoding="utf-8")
        self.assertIn("def notify_action_created", source)
        self.assertIn("def notify_action_pending_verification", source)
        action_source = ACTION_PY.read_text(encoding="utf-8")
        self.assertIn("notify_action_created", action_source)
        self.assertIn("notify_action_pending_verification", action_source)


if __name__ == "__main__":
    unittest.main()
