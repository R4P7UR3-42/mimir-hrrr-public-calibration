import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_refit_successor.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("refit", MODULE_PATH)
refit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refit)


def parent_model():
    return {
        "station_models": [
            {
                "station_id": station,
                "distance_f": distance,
                "samples": 365,
                "successes": 300 - distance,
            }
            for station in refit.economics.STATION_SERIES
            for distance in refit.economics.DISTANCES
        ]
    }


def parent_rows():
    return [
        {"station_id": station, "residual_f": "0" if day < 225 else "99"}
        for day in range(250)
        for station in refit.economics.STATION_SERIES
    ]


class HrrrRefitSuccessorTest(unittest.TestCase):
    def test_frozen_window_model_and_predeclaration_hashes(self):
        root = MODULE_PATH.parents[1]
        self.assertEqual((refit.UNTOUCHED_START, refit.UNTOUCHED_END, refit.UNTOUCHED_DATES), ("2025-07-29", "2026-04-04", 250))
        self.assertEqual(
            len(refit.economics.date_range(refit.date.fromisoformat(refit.UNTOUCHED_START), refit.date.fromisoformat(refit.UNTOUCHED_END))),
            250,
        )
        self.assertEqual(refit.sha256(root / "REFIT_SUCCESSOR_PREDECLARATION.md"), refit.PREDECLARATION_SHA256)
        self.assertEqual(
            refit.sha256(root / "assets/hrrr_v4_station_jeffreys_615_minus_0035_v1.json"),
            refit.MODEL_ARTIFACT_SHA256,
        )

    def test_build_freezes_serialized_scores_and_exact_climatology_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent_report = root / "parent-report.json"
            parent_capture = root / "parent-capture.json"
            development_capture = root / "development-capture.json"
            failed_report = root / "failed-report.json"
            for path in (parent_report, parent_capture, development_capture):
                path.write_text("{}")
            failed = {"evaluation": {"diagnostic_decision": {"passes": False}}}
            failed_report.write_text(json.dumps(failed))
            observed = {}

            def passing_development(_capture, models, baselines, start, end):
                observed.update(models=models, baselines=baselines, start=start, end=end)
                return {"diagnostic_decision": {"passes": True, "gates": {"all": True}}}

            with (
                mock.patch.object(refit, "FAILED_LATER_CAPTURE_SHA256", refit.sha256(development_capture)),
                mock.patch.object(refit, "FAILED_LATER_REPORT_SHA256", refit.sha256(failed_report)),
                mock.patch.object(refit.predecessor, "load_parent", return_value=(parent_model(), {}, {})),
                mock.patch.object(refit.predecessor, "evaluate_later_capture", return_value=failed),
                mock.patch.object(refit.calibration, "load_capture", return_value=parent_rows()),
                mock.patch.object(refit, "evaluate_with_model", side_effect=passing_development),
            ):
                model = refit.build_model(parent_report, parent_capture, development_capture, failed_report)

            first = model["station_models"][0]
            expected_raw = ((Decimal(first["successes"]) + Decimal("0.5")) / Decimal("616")).quantize(refit.SCORE_QUANTUM)
            self.assertEqual(first["samples"], 615)
            self.assertEqual(first["raw_jeffreys_score"], f"{expected_raw:.6f}")
            self.assertEqual(first["corrected_score"], f"{expected_raw - refit.CORRECTION:.6f}")
            self.assertEqual(observed["models"][(first["station_id"], first["distance_f"])], Decimal(first["corrected_score"]))
            self.assertEqual(observed["start"], refit.DEVELOPMENT_START)
            self.assertEqual(observed["end"], refit.DEVELOPMENT_END)
            counts = model["distance_training_climatology_counts"]
            self.assertEqual(counts["4"]["samples"], 615 * len(refit.economics.STATION_SERIES))
            self.assertEqual(
                observed["baselines"][4],
                Decimal(counts["4"]["successes"]) / Decimal(counts["4"]["samples"]),
            )

    def test_model_maps_requires_exact_integer_climatology_and_complete_grid(self):
        model_path = MODULE_PATH.parents[1] / "assets/hrrr_v4_station_jeffreys_615_minus_0035_v1.json"
        model = json.loads(model_path.read_text())
        scores, baselines = refit.model_maps(model)
        self.assertEqual(len(scores), 80)
        self.assertEqual(set(baselines), set(refit.economics.DISTANCES))

        rounded = copy.deepcopy(model)
        rounded.pop("distance_training_climatology_counts")
        rounded["distance_training_climatology"] = {"4": "0.90"}
        with self.assertRaisesRegex(ValueError, "climatology grid"):
            refit.model_maps(rounded)

        malformed = copy.deepcopy(model)
        malformed["distance_training_climatology_counts"]["4"]["samples"] -= 1
        with self.assertRaisesRegex(ValueError, "climatology counts"):
            refit.model_maps(malformed)

    def test_consumed_untouched_workflow_is_retired(self):
        workflow = MODULE_PATH.parents[1] / ".github/workflows/hrrr-refit-untouched-calibration.yml"
        self.assertFalse(workflow.exists())


if __name__ == "__main__":
    unittest.main()
