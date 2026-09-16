import importlib
import sys
import types
import unittest


class FakeDoc:
    def __init__(self, frappe, doctype):
        self._frappe = frappe
        self.doctype = doctype
        self._data = {}
        self.questions = []
        self.name = None

    def update(self, values):
        self._data.update(values)
        for key, value in values.items():
            setattr(self, key, value)

    def append(self, fieldname, value):
        assert fieldname == "questions"
        self.questions.append(dict(value))

    def insert(self, ignore_permissions=False):
        assert ignore_permissions is True
        if self.doctype == "Checklist Question":
            self.name = f"Q-{len(self._frappe.inserted_questions) + 1:04d}"
            self._frappe.inserted_questions.append(self)
        elif self.doctype == "Checklist Question Template":
            self.name = self._data["template_name"]
            self._frappe.inserted_templates.append(self)
        else:
            raise AssertionError(self.doctype)
        return self


class FakeExistingDoc:
    def __init__(self, parent, doctype, name, docstatus):
        self._parent = parent
        self.doctype = doctype
        self.name = name
        self.docstatus = docstatus
        self.flags = types.SimpleNamespace(ignore_permissions=False, ignore_links=False)

    def cancel(self):
        self._parent.cancelled.append((self.doctype, self.name))
        self.docstatus = 2
        self._parent.docstatus[(self.doctype, self.name)] = 2


class FakeDB:
    def __init__(self, parent):
        self.parent = parent
        self.department_exists = True
        self.commits = 0
        self.rollbacks = 0

    def exists(self, doctype, name):
        assert doctype == "Department"
        assert name == "Maintenance - Taj"
        return self.department_exists

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.db = FakeDB(self)
        self.deleted = []
        self.cancelled = []
        self.inserted_questions = []
        self.inserted_templates = []
        self.existing = {
            "Checklist Answer": ["A-2", "A-1"],
            "Checklist Question Template": ["Old Template"],
            "Checklist Question": ["Q-old-2", "Q-old-1"],
        }
        self.docstatus = {
            ("Checklist Answer", "A-2"): 1,
            ("Checklist Answer", "A-1"): 0,
        }

    def throw(self, message):
        raise RuntimeError(message)

    def get_all(self, doctype, pluck=None, order_by=None):
        assert pluck == "name"
        assert order_by == "creation desc"
        return list(self.existing.get(doctype, []))

    def get_doc(self, doctype, name):
        return FakeExistingDoc(self, doctype, name, self.docstatus.get((doctype, name), 0))

    def delete_doc(self, doctype, name, force=0, ignore_permissions=False):
        assert force == 1
        assert ignore_permissions is True
        if self.docstatus.get((doctype, name), 0) == 1:
            raise RuntimeError(f"{doctype} {name}: Submitted Record cannot be deleted")
        self.deleted.append((doctype, name))

    def new_doc(self, doctype):
        return FakeDoc(self, doctype)


class EngineeringMaintenanceSeedRuntimeStubTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeFrappe()
        sys.modules["frappe"] = self.fake
        sys.modules.pop("taj_core.checklist.engineering_maintenance_seed", None)
        self.seed = importlib.import_module("taj_core.checklist.engineering_maintenance_seed")

    def tearDown(self):
        sys.modules.pop("taj_core.checklist.engineering_maintenance_seed", None)
        sys.modules.pop("frappe", None)

    def test_wrong_confirmation_does_not_delete_or_commit(self):
        with self.assertRaisesRegex(RuntimeError, "Destructive Checklist reset blocked"):
            self.seed.replace_all_checklist_data(confirm="no")
        self.assertEqual(self.fake.deleted, [])
        self.assertEqual(self.fake.db.commits, 0)

    def test_missing_department_does_not_delete(self):
        self.fake.db.department_exists = False
        with self.assertRaisesRegex(RuntimeError, "Nothing was deleted"):
            self.seed.replace_all_checklist_data(confirm=self.seed.CONFIRMATION_PHRASE)
        self.assertEqual(self.fake.deleted, [])
        self.assertEqual(self.fake.db.commits, 0)

    def test_success_deletes_in_order_and_creates_21_templates(self):
        result = self.seed.replace_all_checklist_data(confirm=self.seed.CONFIRMATION_PHRASE)

        deleted_doctypes = [doctype for doctype, _ in self.fake.deleted]
        self.assertEqual(
            deleted_doctypes,
            [
                "Checklist Answer",
                "Checklist Answer",
                "Checklist Question Template",
                "Checklist Question",
                "Checklist Question",
            ],
        )
        self.assertEqual(self.fake.cancelled, [("Checklist Answer", "A-2")])
        self.assertEqual(result["templates_created"], 21)
        self.assertEqual(result["questions_created"], len(self.seed.QUESTION_LIBRARY))
        self.assertEqual(len(self.fake.inserted_templates), 21)
        self.assertEqual(self.fake.db.commits, 1)
        self.assertEqual(self.fake.db.rollbacks, 0)

        for template in self.fake.inserted_templates:
            self.assertEqual(template.department, "Maintenance - Taj")
            self.assertEqual(template.assignment_type, "Any User in Department")
            self.assertEqual(template.periodicity, "None")
            self.assertTrue(template.questions)


if __name__ == "__main__":
    unittest.main()
