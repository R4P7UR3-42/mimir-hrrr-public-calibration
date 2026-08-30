import unittest
from pathlib import Path


class HrrrRefitEconomicsWorkflowTest(unittest.TestCase):
    def test_consumed_workflow_is_retired(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / ".github/workflows/hrrr-refit-executable-economics.yml").exists())


if __name__ == "__main__":
    unittest.main()
