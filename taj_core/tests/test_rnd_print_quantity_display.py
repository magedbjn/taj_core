import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "rnd/services/quantity_display.py"


def load_module(testcase):
    if not MODULE_PATH.exists():
        testcase.fail("quantity_display.py does not exist")
    spec = importlib.util.spec_from_file_location("quantity_display", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPrintQuantityDisplay(unittest.TestCase):
    def test_gram_quantity_over_1000_displays_as_kg(self):
        module = load_module(self)
        self.assertEqual(module.format_mass_for_print(2300, "Gram"), ("2.3", "kg"))

    def test_exactly_1000_grams_stays_grams(self):
        module = load_module(self)
        self.assertEqual(module.format_mass_for_print(1000, "Gram"), ("1000", "Gram"))

    def test_non_gram_uom_is_not_converted(self):
        module = load_module(self)
        self.assertEqual(module.format_mass_for_print(2300, "ml"), ("2300", "ml"))

    def test_implicit_gram_field_can_be_formatted(self):
        module = load_module(self)
        self.assertEqual(module.format_mass_for_print(15652.173913, "gm"), ("15.652", "kg"))


if __name__ == "__main__":
    unittest.main()
