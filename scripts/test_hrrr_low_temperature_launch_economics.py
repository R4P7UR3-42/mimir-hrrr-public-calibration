import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_low_temperature_launch_economics.py")
SPEC = importlib.util.spec_from_file_location("low_temperature_launch", MODULE_PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


class LowTemperatureLaunchEconomicsTest(unittest.TestCase):
    def test_exact_window_and_boundaries(self):
        self.assertEqual(launch.WINDOW, ("2026-04-03", "2026-07-23", 112, "launch-window-v1"))
        self.assertEqual(len(launch.prior.low.base.iso_dates(launch.WINDOW[0], launch.WINDOW[1])), 112)
        self.assertEqual(launch.MINIMUM_COMPLETE_DATES, 110)
        self.assertEqual(launch.NETWORK_LIMIT, 10_000)

    def test_exact_url_cache_avoids_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache, output = root / "cache", root / "output"
            (cache / "raw").mkdir(parents=True)
            body = b'{"ok":true}'
            (cache / "raw" / "source.json").write_bytes(body)
            (cache / "raw" / "source.request.json").write_text(json.dumps({
                "request_url": "https://example.test/exact",
                "response_sha256": hashlib.sha256(body).hexdigest(),
            }))
            client = launch.CachedPublicClient(output, launch.NETWORK_LIMIT, cache)
            self.assertEqual(client.fetch("https://example.test/exact", "result"), {"ok": True})
            self.assertEqual(client.cache_hits, 1)
            self.assertEqual(client.used, 0)
            self.assertEqual((output / "raw/result.json").read_bytes(), body)

    def test_inventory_report_is_exact(self):
        result = MODULE_PATH.parents[1] / "data/results/hrrr-v4-low-temperature-economics-v1/report.json"
        self.assertEqual(launch.prior.econ.file_sha256(result), launch.INVENTORY_REPORT_SHA256)

    def test_public_workflow_is_free_and_isolated(self):
        workflow = (MODULE_PATH.parents[1] / ".github/workflows/hrrr-low-temperature-launch-economics.yml").read_text()
        self.assertIn('run-id: "33319871449"', workflow)
        self.assertIn("source_run_id == 33320248649", workflow)
        self.assertIn("capture.tar.gz", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("--max-requests 10000", workflow)
        self.assertNotIn("mimir-hrrr-capture-55e66973 --", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("portfolio", workflow)


if __name__ == "__main__":
    unittest.main()
