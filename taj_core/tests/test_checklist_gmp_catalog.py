import unittest

from taj_core.checklist.gmp_catalog import GMP_QUESTIONS, GMP_TEMPLATES, validate_gmp_catalog


EXPECTED_TEMPLATES = {
    "GMP - Receiving": "1,3",
    "GMP - Dry Store": "1,3",
    "GMP - Chiller": "1,3",
    "GMP - Freezer": "1,3",
    "GMP - Preparation Area": "2,4",
    "GMP - Cooking Area": "2,4",
    "GMP - Filling & Retort Area": "2,4",
    "GMP - Incubation Area": "1,3",
    "GMP - Finished Goods Area": "1,3",
}


class TestChecklistGmpCatalog(unittest.TestCase):
    def test_catalog_is_valid_and_covers_full_non_duplicate_source(self):
        self.assertEqual(validate_gmp_catalog(), [])
        self.assertEqual(len(GMP_QUESTIONS), 50)
        total_assignments = sum(len(template["questions"]) for template in GMP_TEMPLATES.values())
        self.assertEqual(total_assignments, 159)

    def test_catalog_has_nine_expected_area_templates_and_week_patterns(self):
        self.assertEqual(set(GMP_TEMPLATES), set(EXPECTED_TEMPLATES))
        for name, weeks in EXPECTED_TEMPLATES.items():
            self.assertEqual(GMP_TEMPLATES[name]["weeks_of_month"], weeks)
            self.assertEqual(GMP_TEMPLATES[name]["periodicity"], "Weeks of Month")
            self.assertGreaterEqual(len(GMP_TEMPLATES[name]["questions"]), 7)

    def test_question_text_is_unique_positive_and_has_group_and_reference(self):
        texts = []
        for key, question in GMP_QUESTIONS.items():
            self.assertTrue(key)
            text = question["question"].strip()
            texts.append(text)
            self.assertTrue(text)
            self.assertFalse(text.endswith("?"), text)
            self.assertTrue(question["question_group"].strip())
            self.assertTrue(question["standard_reference"].strip())
            standards = question["standards"]
            self.assertGreaterEqual(len(standards), 2)
            names = {row["standard"] for row in standards}
            self.assertIn("GMP", names)
            self.assertIn("ISO 22000", names)
            iso = next(row for row in standards if row["standard"] == "ISO 22000")
            self.assertTrue(iso["reference"].strip())
        self.assertEqual(len(texts), len(set(texts)))

    def test_broad_gmp_questions_define_failure_scope_without_exploding_question_count(self):
        facility_clean = GMP_QUESTIONS["facility_cleanliness"]
        self.assertEqual(facility_clean["require_affected_item"], 1)
        self.assertIn("Light Fixture", facility_clean["affected_item_options"].splitlines())
        self.assertEqual(facility_clean["require_issue_type"], 1)
        self.assertIn("Cleaning", facility_clean["issue_type_options"].splitlines())

        facility_condition = GMP_QUESTIONS["facility_condition"]
        self.assertIn("Electrical", facility_condition["issue_type_options"].splitlines())

        equipment = GMP_QUESTIONS["equipment_condition"]
        self.assertIn("Rack", equipment["affected_item_options"].splitlines())
        self.assertIn("Rust / Corrosion", equipment["issue_type_options"].splitlines())

        # Scope details appear only after Fail while all non-duplicate workbook rows remain covered.
        self.assertEqual(len(GMP_QUESTIONS), 50)
        total_assignments = sum(len(template["questions"]) for template in GMP_TEMPLATES.values())
        self.assertEqual(total_assignments, 159)

    def test_compound_wording_updates_keep_legacy_question_ids_reusable(self):
        for key in (
            "ventilation_effective",
            "exposed_product_protected",
            "food_contact_sanitized",
            "cleaning_tools_hygienic",
            "equipment_condition",
            "personnel_hygiene",
        ):
            self.assertTrue(GMP_QUESTIONS[key].get("legacy_questions"), key)

    def test_all_template_question_keys_exist_without_duplicates(self):
        for name, template in GMP_TEMPLATES.items():
            keys = template["questions"]
            self.assertEqual(len(keys), len(set(keys)), name)
            for key in keys:
                self.assertIn(key, GMP_QUESTIONS, f"{name}: {key}")

    def test_source_specific_checks_are_kept_once_and_reused_by_templates(self):
        texts = "\n".join(item["question"].lower() for item in GMP_QUESTIONS.values())
        self.assertIn("pest trap labels", texts)
        self.assertIn("not designated for use in that area", texts)
        self.assertIn("walls, light fixtures, racks and floors are free from dust", texts)
        self.assertNotIn("are walls, lights/light fixtures, racks and floors free from dust", texts)



if __name__ == "__main__":
    unittest.main()
