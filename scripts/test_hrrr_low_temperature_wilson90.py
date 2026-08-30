import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_low_temperature_wilson90.py")
SPEC = importlib.util.spec_from_file_location("low_temperature_wilson90", MODULE_PATH)
low = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(low)


class LowTemperatureWilson90Test(unittest.TestCase):
    def test_frozen_successor_identity(self):
        self.assertEqual(low.EVALUATION, ("2024-11-21", "2025-07-28", 250, "33300096256"))
        self.assertEqual(low.WILSON_Z, Decimal("1.2815515655446004"))
        self.assertEqual(low.MINIMUM_COMPLETE_DATES, 245)
        self.assertEqual(len(low.base.iso_dates(low.EVALUATION[0], low.EVALUATION[1])), 250)

    def test_frozen_model_is_complete_and_checksum_bound(self):
        payload = json.loads(low.model_path().read_text())
        stations = sorted({row["station_id"] for row in payload["station_models"]})
        model, model_map, baselines = low.load_frozen_model(stations)
        self.assertEqual(model["schema"], low.MODEL_SCHEMA)
        self.assertEqual(len(stations), 20)
        self.assertEqual(len(model_map), 80)
        self.assertEqual(set(baselines), {4, 5, 6, 7})

    def test_missing_value_excludes_entire_date(self):
        identity = {"KAAA": "GHCN1", "KBBB": "GHCN2"}
        prior = low.EVALUATION
        low.EVALUATION = ("2024-01-01", "2024-01-02", 2, "run")
        try:
            body = json.dumps(
                [
                    {"STATION": "GHCN1", "DATE": "2024-01-01", "TMIN": "10"},
                    {"STATION": "GHCN2", "DATE": "2024-01-01"},
                    {"STATION": "GHCN1", "DATE": "2024-01-02", "TMIN": "11"},
                    {"STATION": "GHCN2", "DATE": "2024-01-02", "TMIN": "12"},
                ]
            ).encode()
            outcomes, exclusions, complete = low.parse_whole_dates(body, identity)
        finally:
            low.EVALUATION = prior
        self.assertEqual(complete, ["2024-01-02"])
        self.assertEqual(set(outcomes), {("KAAA", "2024-01-02"), ("KBBB", "2024-01-02")})
        self.assertEqual(exclusions[0]["market_date"], "2024-01-01")
        self.assertEqual(exclusions[0]["issues"], [{"reason": "missing_tmin", "station_id": "KBBB"}])

    def test_no_paid_or_private_dependency(self):
        workflow = MODULE_PATH.parents[1] / ".github/workflows/hrrr-low-temperature-wilson90.yml"
        self.assertFalse(workflow.exists(), "consumed one-shot network workflow must remain retired")
        source = MODULE_PATH.read_text()
        self.assertNotIn("external-api.kalshi.com", source)
        self.assertNotIn("secrets.", source)


if __name__ == "__main__":
    unittest.main()
