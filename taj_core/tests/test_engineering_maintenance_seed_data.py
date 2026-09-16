import importlib
import unittest


EXPECTED_TITLES = {
    "ENG-PM-0001": "SOLPAC Machine Maintenance",
    "ENG-PM-0002": "Anristu Machines Maintenance",
    "ENG-PM-0003": "Retort Sterilizer Maintenance",
    "ENG-PM-0004": "Mini Retort Maintenance",
    "ENG-PM-0005": "Cooking Kettles Maintenance",
    "ENG-PM-0006": "Bowl Cutter Maintenance",
    "ENG-PM-0007": "Meat Mincer Maintenance",
    "ENG-PM-0008": "Vegetable Peeler Maintenance",
    "ENG-PM-0009": "Vegetable Blender Maintenance",
    "ENG-PM-0010": "Vegetable Slicer Maintenance",
    "ENG-PM-0011": "Meat Cubing Maintenance",
    "ENG-PM-0012": "Air Operated Pump Maintenance",
    "ENG-PM-0013": "Inline Metal Detector Maintenance",
    "ENG-PM-0014": "Check-Weigher Maintenance",
    "ENG-PM-0015": "Vacuum Packing Machine Maintenance",
    "ENG-PM-0016": "Hand Blender Maintenance",
    "ENG-PM-0017": "Bin Lifter Maintenance",
    "ENG-PM-0018": "Conveyor Maintenance",
    "ENG-PM-0019": "Flattener Maintenance",
    "ENG-PM-0020": "Inject Printer Maintenance",
    "ENG-PM-0021": "Exhaust & Fresh Air Systems Maintenance",
}


class EngineeringMaintenanceSeedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = importlib.import_module("taj_core.checklist.engineering_maintenance_data")

    def test_contains_all_21_source_templates_in_code_order(self):
        templates = self.data.TEMPLATES
        self.assertEqual(len(templates), 21)
        self.assertEqual(
            [row["code"] for row in templates],
            [f"ENG-PM-{i:04d}" for i in range(1, 22)],
        )
        self.assertEqual({row["code"]: row["template_name"] for row in templates}, EXPECTED_TITLES)

    def test_question_wording_is_concise_not_copied_as_instructions(self):
        banned_prefixes = ("check ", "checking ", "make sure ", "is ", "are ")
        for key, spec in self.data.QUESTION_LIBRARY.items():
            text = spec["question"].strip()
            self.assertTrue(text, key)
            self.assertLessEqual(len(text), 64, f"{key}: {text}")
            self.assertFalse(text.lower().startswith(banned_prefixes), f"{key}: {text}")

    def test_every_template_references_defined_unique_questions(self):
        library = self.data.QUESTION_LIBRARY
        for template in self.data.TEMPLATES:
            keys = template["question_keys"]
            self.assertEqual(len(keys), len(set(keys)), template["template_name"])
            self.assertGreaterEqual(len(keys), 4, template["template_name"])
            self.assertTrue(set(keys).issubset(library), template["template_name"])

    def test_shared_source_metadata_and_cleaning_rule_are_reused(self):
        for template in self.data.TEMPLATES:
            keys = template["question_keys"]
            self.assertEqual(keys[0], "maintenance_reason")
            self.assertIn("area_cleaned_after_maintenance", keys)
            self.assertEqual(keys[-1], "maintenance_notes")

    def test_common_questions_are_reused_instead_of_duplicated(self):
        usage = {}
        for template in self.data.TEMPLATES:
            for key in template["question_keys"]:
                usage[key] = usage.get(key, 0) + 1
        self.assertGreaterEqual(usage["machine_cleanliness"], 10)
        self.assertGreaterEqual(usage["electrical_supply_220"], 8)
        self.assertGreaterEqual(usage["switches_controls"], 8)

    def test_same_belt_condition_concepts_reuse_question_keys(self):
        by_code = {row["code"]: row for row in self.data.TEMPLATES}
        self.assertIn("belt_condition", by_code["ENG-PM-0014"]["question_keys"])
        self.assertIn("belt_bearings", by_code["ENG-PM-0018"]["question_keys"])
        self.assertIn("belt_bearings", by_code["ENG-PM-0019"]["question_keys"])
        self.assertNotIn("conveyor_belt_condition", self.data.QUESTION_LIBRARY)
        self.assertNotIn("belts_bearings", self.data.QUESTION_LIBRARY)

    def test_pressure_questions_keep_source_ranges_as_numeric_limits(self):
        expected = {
            "air_pressure_6_7": (6.0, 7.0),
            "air_pressure_4_4_5": (4.0, 4.5),
            "air_pressure_8_9": (8.0, 9.0),
            "air_pressure_3_4": (3.0, 4.0),
            "air_pressure_2_4": (2.0, 4.0),
            "steam_pressure_4_5": (4.0, 5.0),
            "steam_pressure_2_3": (2.0, 3.0),
        }
        for key, (minimum, maximum) in expected.items():
            spec = self.data.QUESTION_LIBRARY[key]
            self.assertEqual(spec["type"], "Float")
            self.assertEqual(spec["answer_min_float"], minimum)
            self.assertEqual(spec["answer_max_float"], maximum)
            self.assertEqual(spec["quick_pass_allowed"], 0)

    def test_reviewed_template_repairs_are_targeted_and_preserve_schedule(self):
        repairs = self.data.REVIEWED_TEMPLATE_REPAIRS
        self.assertEqual(
            repairs["Vegetable Slicer Maintenance"],
            {"department": "Maintenance - Taj"},
        )
        self.assertEqual(
            repairs["Cooking Kettles Maintenance"],
            {"assignment_type": "Any User in Department", "assigned_user": None},
        )
        self.assertEqual(
            repairs["Vacuum Packing Machine Maintenance"],
            {
                "enable_worker_check": 0,
                "required_worker_count": 0,
                "default_worker_company": None,
                "default_worker_supplier": None,
                "worker_failure_reason_options": None,
            },
        )
        forbidden = {"periodicity", "schedule_time", "enable_time_control", "next_due_date", "questions", "asset"}
        for values in repairs.values():
            self.assertTrue(forbidden.isdisjoint(values))

    def test_data_self_validation_reports_no_errors(self):
        self.assertEqual(self.data.validate_seed_data(), [])


if __name__ == "__main__":
    unittest.main()
