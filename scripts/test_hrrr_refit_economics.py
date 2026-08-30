import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_refit_economics.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("refit_economics", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class HrrrRefitEconomicsTest(unittest.TestCase):
    def test_predeclaration_freezes_exact_trigger_window_and_policy(self):
        root = MODULE_PATH.parents[1]
        self.assertEqual(audit.CALIBRATION_RUN_ID, "33307452119")
        self.assertEqual(audit.CALIBRATION_HEAD_SHA, "06208135423e919f7a7966166e4ae9f720c85a4b")
        self.assertEqual((audit.START.isoformat(), audit.END.isoformat()), ("2025-07-29", "2026-04-04"))
        self.assertEqual(len(audit.economics.date_range(audit.START, audit.END)), 250)
        self.assertEqual(
            audit.refit.sha256(root / "REFIT_EXECUTABLE_ECONOMICS_PREDECLARATION.md"),
            audit.PREDECLARATION_SHA256,
        )
        self.assertEqual(audit.NETWORK_LIMIT, 12_000)
        self.assertEqual(
            (audit.economics.MIN_PRICE, audit.economics.MAX_PRICE, audit.economics.MIN_EDGE),
            (audit.Decimal("0.70"), audit.Decimal("0.97"), audit.Decimal("0.015")),
        )

    def test_expected_report_is_non_authorizing_and_uses_only_frozen_model(self):
        model_path = MODULE_PATH.parents[1] / "assets/hrrr_v4_station_jeffreys_615_minus_0035_v1.json"
        model = json.loads(model_path.read_text())
        evaluation = {"diagnostic_decision": {"passes": True, "gates": {"all": True}}}
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.json"
            capture.write_text("{}")
            with mock.patch.object(audit.refit, "evaluate_with_model", return_value=evaluation) as evaluate:
                report = audit.expected_untouched_report(model, model_path, capture)
        self.assertIs(report["research_only"], True)
        self.assertIs(report["historical_price_data_inspected"], False)
        self.assertIs(report["provider_confirmed_fill_evidence"], False)
        self.assertIs(report["capital_risk_authority"], False)
        self.assertIs(report["production_activation"], False)
        self.assertEqual(evaluate.call_args.args[3:], (audit.refit.UNTOUCHED_START, audit.refit.UNTOUCHED_END))

    def test_wrong_run_identity_rejects_before_model_or_network_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run.json"
            run.write_text(json.dumps({
                "schema": audit.RUN_SCHEMA,
                "run_id": "33307452120",
                "head_sha": audit.CALIBRATION_HEAD_SHA,
                "research_only": True,
                "active_trading_capability_changed": False,
                "automatic_production_activation": False,
            }))
            with mock.patch.object(audit.refit, "build_model") as build:
                with self.assertRaisesRegex(ValueError, "run identity"):
                    audit.verify_untouched(
                        Path("parent-report"), Path("parent-capture"), Path("development"), Path("failed"),
                        Path("model"), run, Path("untouched"), Path("report"),
                    )
            build.assert_not_called()

    def test_failed_calibration_cannot_construct_public_client(self):
        constructed = []

        def client_factory(*args):
            constructed.append(args)
            raise AssertionError("client must remain unreachable")

        with mock.patch.object(audit, "verify_untouched", side_effect=ValueError("frozen gate failed")):
            with self.assertRaisesRegex(ValueError, "frozen gate failed"):
                audit.run_economics(
                    *(Path(str(index)) for index in range(8)),
                    Path("output"),
                    audit.NETWORK_LIMIT,
                    client_factory,
                )
        self.assertEqual(constructed, [])


if __name__ == "__main__":
    unittest.main()
