import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "rnd"
    / "services"
    / "snapshot_compare.py"
)

if not MODULE_PATH.exists():
    raise AssertionError(f"Missing snapshot normalization helper: {MODULE_PATH}")

spec = importlib.util.spec_from_file_location("snapshot_compare", MODULE_PATH)
snapshot_compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot_compare)
normalize_snapshot_value = snapshot_compare.normalize_snapshot_value
snapshot_values_equal = snapshot_compare.snapshot_values_equal


class TestRNDSolidLiquidSnapshotCompare(unittest.TestCase):
    def test_numeric_formatting_does_not_count_as_snapshot_change(self):
        self.assertTrue(snapshot_values_equal("weight", 20, 20.0))
        self.assertTrue(snapshot_values_equal("ph", "6.20", 6.2))
        self.assertTrue(snapshot_values_equal("salt", None, 0))

    def test_real_numeric_change_is_detected(self):
        self.assertFalse(snapshot_values_equal("weight", 20, 21))

    def test_text_change_is_detected(self):
        self.assertTrue(snapshot_values_equal("component_name", "Potato", "Potato"))
        self.assertFalse(snapshot_values_equal("component_name", "Potato", "Carrot"))

    def test_signature_normalization_uses_numeric_values(self):
        self.assertEqual(normalize_snapshot_value("weight", 20), 20.0)
        self.assertEqual(normalize_snapshot_value("weight", 20.0), 20.0)
        self.assertEqual(normalize_snapshot_value("total_weight_cook", None), 0.0)
        self.assertEqual(normalize_snapshot_value("component_type", None), "")


if __name__ == "__main__":
    unittest.main()
