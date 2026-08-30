import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_conservative_successor.py")
SPEC = importlib.util.spec_from_file_location("successor", MODULE_PATH)
successor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(successor)


class ConservativeSuccessorTest(unittest.TestCase):
    def test_frozen_identity(self):
        self.assertEqual(successor.CORRECTION, Decimal("0.035"))
        self.assertEqual(successor.SCORE_FLOOR, Decimal("0.900"))
        self.assertEqual(successor.WINDOWS["oos"], ("2024-03-16", "2024-11-20", 250))
        self.assertEqual(len(successor.RELIABILITY_BANDS), 3)

    def test_date_window_is_exact(self):
        self.assertEqual(len(successor.iso_dates("2024-03-16", "2024-11-20")), 250)
        self.assertEqual(successor.iso_dates("2024-03-16", "2024-03-17"), ["2024-03-16", "2024-03-17"])

    def test_cluster_bootstrap_is_deterministic_and_whole_date(self):
        rows = [("2024-01-01", Decimal("0.1")), ("2024-01-01", Decimal("0.3")), ("2024-01-02", Decimal("0.5"))]
        first = successor.clustered_lower(rows, Decimal("0.05"), 1000)
        second = successor.clustered_lower(rows, Decimal("0.05"), 1000)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, Decimal("0.1"))
        self.assertLessEqual(first, Decimal("0.5"))


if __name__ == "__main__":
    unittest.main()
