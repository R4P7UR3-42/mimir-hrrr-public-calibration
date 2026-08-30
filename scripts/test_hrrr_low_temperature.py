import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_low_temperature.py")
SPEC = importlib.util.spec_from_file_location("low_temperature", MODULE_PATH)
low = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(low)


class LowTemperatureCalibrationTest(unittest.TestCase):
    def test_frozen_identity_and_wilson_boundary(self):
        self.assertEqual(low.TRAINING, ("2023-07-10", "2024-03-15", 250, "33204106231"))
        self.assertEqual(low.EVALUATION, ("2024-03-16", "2024-11-20", 250, "33291428414"))
        self.assertEqual(low.DISTANCES, (4, 5, 6, 7))
        self.assertEqual(low.SCORE_FLOOR, Decimal("0.900000"))
        self.assertEqual(low.wilson_lower(250, 250), Decimal("0.989294"))
        self.assertEqual(low.wilson_lower(240, 250), Decimal("0.934209"))
        self.assertLess(low.wilson_lower(230, 250), low.SCORE_FLOOR)

    def test_date_windows_are_exact(self):
        self.assertEqual(len(low.iso_dates(low.TRAINING[0], low.TRAINING[1])), 250)
        self.assertEqual(len(low.iso_dates(low.EVALUATION[0], low.EVALUATION[1])), 250)

    def test_cluster_sampler_is_deterministic_and_resamples_dates(self):
        rows = [
            ("2024-01-01", Decimal("0.1")),
            ("2024-01-01", Decimal("0.3")),
            ("2024-01-02", Decimal("0.5")),
        ]
        first = low.clustered_lower(rows, Decimal("0.05"), 1_000)
        second = low.clustered_lower(rows, Decimal("0.05"), 1_000)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, Decimal("0.1"))
        self.assertLessEqual(first, Decimal("0.5"))

    def test_tmin_parser_requires_complete_exact_identity(self):
        identity = {"KAAA": "USW00000001"}
        expected = ("2024-01-01", "2024-01-02", 2, "run")
        body = json.dumps(
            [
                {"STATION": "USW00000001", "DATE": "2024-01-01", "TMIN": "20"},
                {"STATION": "USW00000001", "DATE": "2024-01-02", "TMIN": "21"},
            ]
        ).encode()
        parsed = low.parse_outcomes(body, identity, expected)
        self.assertEqual(parsed[("KAAA", "2024-01-01")], Decimal("20"))
        with self.assertRaisesRegex(ValueError, "coverage is incomplete"):
            low.parse_outcomes(json.dumps(json.loads(body)[:1]).encode(), identity, expected)
        with self.assertRaisesRegex(ValueError, "outside the frozen identity"):
            low.parse_outcomes(
                json.dumps(json.loads(body) + [{"STATION": "OTHER", "DATE": "2024-01-01", "TMIN": "20"}]).encode(),
                identity,
                expected,
            )

    def test_grid_reader_rejects_duplicate_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stations = [f"K{index:03d}" for index in range(20)]
            identities = [
                {"stationId": station, "ghcnStationId": f"USW{index:08d}"}
                for index, station in enumerate(stations)
            ]
            capture = {
                "schema": low.CAPTURE_SCHEMA,
                "research_only": True,
                "active_trading_capability_changed": False,
                "automatic_production_activation": False,
                "coverage": {"independent_market_dates": 1, "complete_station_dates": 20, "complete": True},
                "design": {
                    "start_market_date": "2024-01-01",
                    "end_market_date": "2024-01-01",
                    "forecast_model": "hrrr_v4_archive_3km_native_3h_nearest_v1",
                    "forecast_availability_basis": "hrrr_12z_operational_2000z_upper_bound_v1",
                },
                "station_identities": identities,
            }
            (root / "capture.json").write_text(json.dumps(capture))
            (root / "hrrr-v4").mkdir()
            points = [{"step_hours": 18, "temperature_f": "10"} for _ in range(8)]
            extraction = {
                "schema": low.EXTRACTION_SCHEMA,
                "market_date": "2024-01-01",
                "forecast_available_at": "2023-12-31T20:00:00.000Z",
                "forecast_availability_basis": "hrrr_12z_operational_2000z_upper_bound_v1",
                "station_forecasts": [
                    {"station_id": station, "grid_points": points} for station in stations
                ],
            }
            (root / "hrrr-v4" / "2024-01-01.json").write_text(json.dumps(extraction))
            with self.assertRaisesRegex(ValueError, "step is duplicated"):
                low.load_forecast_minima(root, ("2024-01-01", "2024-01-01", 1, "run"))

    def test_public_workflow_stays_isolated(self):
        workflow = (MODULE_PATH.parents[1] / ".github/workflows/hrrr-low-temperature-calibration.yml").read_text()
        self.assertIn('run-id: "33204106231"', workflow)
        self.assertIn('run-id: "33291428414"', workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("external-api.kalshi.com", workflow)


if __name__ == "__main__":
    unittest.main()
