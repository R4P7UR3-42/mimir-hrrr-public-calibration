import unittest
from pathlib import Path


class HrrrRefitEconomicsWorkflowTest(unittest.TestCase):
    def test_workflow_is_exactly_triggered_and_hard_gates_before_price_access(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/hrrr-refit-executable-economics.yml").read_text()
        self.assertIn("Frozen 615-date HRRRv4 refit untouched calibration", workflow)
        self.assertIn("github.event.workflow_run.id == 33307452119", workflow)
        self.assertIn("github.event.workflow_run.head_sha == '06208135423e919f7a7966166e4ae9f720c85a4b'", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("ref: c2bb7bd979af89be59188e7911b418132f153dba", workflow)
        self.assertIn("test \"$(git rev-parse HEAD)\" = c2bb7bd979af89be59188e7911b418132f153dba", workflow)
        self.assertIn("hrrrv4-refit-untouched-33307452119", workflow)
        self.assertLess(
            workflow.index("Hard gate exact untouched calibration before price access"),
            workflow.index("Acquire bounded public price and trade evidence"),
        )
        self.assertIn("--max-requests 12000", workflow)
        self.assertIn("/var/tmp/mimir-hrrr-refit-economics", workflow)
        self.assertNotIn("--output-dir /tmp/", workflow)


if __name__ == "__main__":
    unittest.main()
