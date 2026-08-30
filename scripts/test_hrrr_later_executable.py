import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_later_executable.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("later", MODULE_PATH)
later = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(later)


def dates(start: date, count: int):
    return [start + timedelta(days=index) for index in range(count)]


def write_artifacts(root: Path):
    gates = {
        "exact_365_training_dates": True,
        "exact_250_evaluation_dates": True,
        "at_least_100_selected_dates": True,
        "at_least_8_selected_stations": True,
        "positive_brier_skill": True,
        "exact_three_reliability_bands": True,
        "every_reliability_band_ready": True,
        "date_clustered_90_margin_nonnegative": True,
        "date_clustered_95_margin_nonnegative": True,
        "station_concentration_at_most_0_35": True,
        "date_concentration_at_most_0_05": True,
        "exact_20_station_holdouts": True,
        "every_station_holdout_passes": True,
    }
    stations = list(later.economics.STATION_SERIES)
    scores = {
        station: ("0.910000" if index < 7 else "0.935000" if index < 14 else "0.960000")
        for index, station in enumerate(stations)
    }
    station_models = [
        {
            "station_id": station,
            "distance_f": distance,
            "samples": 365,
            "successes": 300,
            "raw_jeffreys_score": str(float(scores[station]) + 0.035),
            "corrected_score": scores[station],
        }
        for station in stations
        for distance in later.economics.DISTANCES
    ]
    report = {
        "schema": later.economics.OOS_SCHEMA,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "design": {
            "model": later.MODEL,
            "mode": "oos",
            "evaluation_start_market_date": later.economics.START.isoformat(),
            "evaluation_end_market_date": later.economics.END.isoformat(),
            "correction": "0.035000",
            "score_floor": "0.900000",
            "distances_f": list(later.economics.DISTANCES),
        },
        "station_models": station_models,
        "evaluation": {
            "selected_independent_market_dates": 250,
            "selected_stations": 20,
            "diagnostic_decision": {"passes": True, "gates": gates},
        },
    }
    parent_rows = []
    for market_date in dates(later.economics.START, 250):
        for station in stations:
            parent_rows.append({
                "station_id": station,
                "market_date": market_date.isoformat(),
                "forecast_model": "hrrr_v4_archive_3km_native_3h_nearest_v1",
                "forecast_availability_basis": "hrrr_12z_operational_2000z_upper_bound_v1",
                "forecast_available_at": (market_date - timedelta(days=1)).isoformat() + "T20:00:00.000Z",
                "forecast_high_f": "80.0",
                "observed_high_f": "80.0",
                "observation_source": "noaa_ncei_daily_summaries_tmax",
            })
    parent_capture = {
        "schema": later.economics.CAPTURE_SCHEMA,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "coverage": {"independent_market_dates": 250, "complete_station_dates": 5000, "complete": True},
        "rows": parent_rows,
    }
    later_rows = []
    for date_index, market_date in enumerate(dates(later.START, later.DATE_COUNT)):
        for station in stations:
            winning_dates = {"0.910000": 228, "0.935000": 234, "0.960000": 240}[scores[station]]
            later_rows.append({
                "station_id": station,
                "market_date": market_date.isoformat(),
                "forecast_model": "hrrr_v4_archive_3km_native_3h_nearest_v1",
                "forecast_availability_basis": "hrrr_12z_operational_2000z_upper_bound_v1",
                "forecast_source_composite_sha256": "a" * 64,
                "observation_source": "noaa_ncei_daily_summaries_tmax",
                "residual_f": "0" if date_index < winning_dates else "99",
            })
    later_capture = {
        "schema": later.calibration.CAPTURE_SCHEMA,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "rows": later_rows,
    }
    report_path = root / "parent-report.json"
    parent_capture_path = root / "parent-capture.json"
    later_capture_path = root / "later-capture.json"
    report_path.write_text(json.dumps(report))
    parent_capture_path.write_text(json.dumps(parent_capture))
    later_capture_path.write_text(json.dumps(later_capture))
    return report_path, parent_capture_path, later_capture_path


class LaterExecutableTest(unittest.TestCase):
    def test_frozen_window_and_predeclaration(self):
        self.assertEqual((later.START.isoformat(), later.END.isoformat(), later.DATE_COUNT), ("2024-11-21", "2025-07-28", 250))
        self.assertEqual(len(later.economics.date_range(later.START, later.END)), 250)
        predeclaration = MODULE_PATH.parents[1] / "LATER_EXECUTABLE_PREDECLARATION.md"
        self.assertEqual(later.economics.file_sha256(predeclaration), later.PREDECLARATION_SHA256)

    def test_later_capture_uses_frozen_parent_scores_and_passes_exact_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            report, parent_capture, later_capture = write_artifacts(Path(temporary))
            with (
                mock.patch.object(later, "PARENT_REPORT_SHA256", later.economics.file_sha256(report)),
                mock.patch.object(later, "PARENT_CAPTURE_SHA256", later.economics.file_sha256(parent_capture)),
                mock.patch.object(later.calibration, "clustered_lower", side_effect=lambda rows, _tail: sum((value for _, value in rows), start=later.Decimal(0)) / len(rows)),
            ):
                result = later.evaluate_later_capture(report, parent_capture, later_capture)
            self.assertTrue(result["evaluation"]["diagnostic_decision"]["passes"])
            self.assertEqual(result["evaluation"]["selected_independent_market_dates"], 250)
            self.assertEqual(result["evaluation"]["selected_stations"], 20)
            self.assertTrue(all(row["ready"] for row in result["evaluation"]["reliability"]))

    def test_failed_later_gate_prevents_client_construction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, parent_capture, later_capture = write_artifacts(root)
            with (
                mock.patch.object(later, "PARENT_REPORT_SHA256", later.economics.file_sha256(report)),
                mock.patch.object(later, "PARENT_CAPTURE_SHA256", later.economics.file_sha256(parent_capture)),
                mock.patch.object(later.calibration, "clustered_lower", side_effect=lambda rows, _tail: sum((value for _, value in rows), start=later.Decimal(0)) / len(rows)),
            ):
                result = later.evaluate_later_capture(report, parent_capture, later_capture)
                result["evaluation"]["diagnostic_decision"]["passes"] = False
                calibration_report = root / "calibration.json"
                calibration_report.write_text(json.dumps(result))
                constructed = []

                def forbidden_client(*args):
                    constructed.append(args)
                    raise AssertionError("network client must not be constructed")

                with self.assertRaisesRegex(ValueError, "does not exactly reproduce|did not pass"):
                    later.run_economics(
                        report,
                        parent_capture,
                        later_capture,
                        calibration_report,
                        root / "economics",
                        later.NETWORK_LIMIT,
                        forbidden_client,
                    )
                self.assertEqual(constructed, [])

    def test_workflow_separates_weather_gate_from_price_access(self):
        root = MODULE_PATH.parents[1]
        weather = (root / ".github/workflows/hrrr-later-executable-calibration.yml").read_text()
        price = (root / ".github/workflows/hrrr-later-executable-economics.yml").read_text()
        self.assertNotIn("api.elections.kalshi.com", weather)
        self.assertIn("--start-date 2024-11-21 --end-date 2025-07-28", weather)
        self.assertIn("workflows:\n      - Later-window frozen HRRRv4 calibration", price)
        self.assertLess(price.index("Hard gate exact later calibration before price access"), price.index("Acquire bounded public price and trade evidence"))
        self.assertIn("github.event.workflow_run.head_branch == 'main'", price)


if __name__ == "__main__":
    unittest.main()
