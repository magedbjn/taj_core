import json
from pathlib import Path
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class SensoryProductServerManagedTest(unittest.TestCase):
    def test_product_is_not_exposed_in_sensory_rating_web_form(self):
        path = PACKAGE_ROOT / "rnd" / "web_form" / "sensory_rating" / "sensory_rating.json"
        data = json.loads(path.read_text())
        fieldnames = [field.get("fieldname") for field in data["web_form_fields"]]
        self.assertNotIn("item", fieldnames)

    def test_product_is_derived_from_selected_trial_on_server(self):
        path = PACKAGE_ROOT / "rnd" / "doctype" / "sensory_feedback" / "sensory_feedback.py"
        source = path.read_text()
        self.assertIn("self.item = trial_proposal", source)
        self.assertNotIn("if trial_proposal !=", source)


if __name__ == "__main__":
    unittest.main()
