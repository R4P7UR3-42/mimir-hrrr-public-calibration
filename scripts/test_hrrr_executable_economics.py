import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_executable_economics.py")
SPEC = importlib.util.spec_from_file_location("economics", MODULE_PATH)
economics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(economics)


def passing_artifacts(root: Path):
    gates = {
        "exact_365_training_dates": True, "exact_250_evaluation_dates": True,
        "at_least_100_selected_dates": True, "at_least_8_selected_stations": True,
        "positive_brier_skill": True, "exact_three_reliability_bands": True,
        "every_reliability_band_ready": True, "date_clustered_90_margin_nonnegative": True,
        "date_clustered_95_margin_nonnegative": True, "station_concentration_at_most_0_35": True,
        "date_concentration_at_most_0_05": True, "exact_20_station_holdouts": True,
        "every_station_holdout_passes": True,
    }
    report = {
        "schema": economics.OOS_SCHEMA, "research_only": True,
        "active_trading_capability_changed": False, "automatic_production_activation": False,
        "design": {
            "model": economics.MODEL, "mode": "oos",
            "evaluation_start_market_date": economics.START.isoformat(),
            "evaluation_end_market_date": economics.END.isoformat(),
            "correction": "0.035000", "score_floor": "0.900000",
            "distances_f": list(economics.DISTANCES),
        },
        "station_models": [
            {"station_id": station, "distance_f": distance, "corrected_score": "0.910000"}
            for station in economics.STATION_SERIES for distance in economics.DISTANCES
        ],
        "evaluation": {
            "selected_independent_market_dates": 250, "selected_stations": 20,
            "diagnostic_decision": {"passes": True, "gates": gates},
        },
    }
    rows = []
    current = economics.START
    while current <= economics.END:
        for station in economics.STATION_SERIES:
            rows.append({
                "station_id": station, "market_date": current.isoformat(),
                "forecast_model": "hrrr_v4_archive_3km_native_3h_nearest_v1",
                "forecast_availability_basis": "hrrr_12z_operational_2000z_upper_bound_v1",
                "forecast_available_at": (current - timedelta(days=1)).isoformat() + "T20:00:00.000Z",
                "forecast_high_f": "80.25", "observed_high_f": "82",
                "observation_source": "noaa_ncei_daily_summaries_tmax",
            })
        current += timedelta(days=1)
    capture = {
        "schema": economics.CAPTURE_SCHEMA, "research_only": True,
        "active_trading_capability_changed": False, "automatic_production_activation": False,
        "coverage": {"independent_market_dates": 250, "complete_station_dates": 5000, "complete": True},
        "rows": rows,
    }
    report_path, capture_path = root / "evaluation.json", root / "capture.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    return report_path, capture_path, report


class ExecutableEconomicsTest(unittest.TestCase):
    class FakeClient:
        def __init__(self, payload):
            self.payload = payload
            self.urls = []

        def fetch(self, url, _label):
            self.urls.append(url)
            return copy.deepcopy(self.payload)

    def test_frozen_boundaries_and_predeclaration(self):
        self.assertEqual(economics.OOS_RUN_ID, "33291428414")
        self.assertEqual((economics.START.isoformat(), economics.END.isoformat(), economics.DATE_COUNT), ("2024-03-16", "2024-11-20", 250))
        self.assertEqual(economics.MIN_PRICE, Decimal("0.70"))
        self.assertEqual(economics.MAX_PRICE, Decimal("0.97"))
        self.assertEqual(economics.MIN_EDGE, Decimal("0.015"))
        predeclaration = MODULE_PATH.parents[1] / "ECONOMICS_PREDECLARATION.md"
        self.assertEqual(economics.file_sha256(predeclaration), economics.PREDECLARATION_SHA256)

    def test_consumed_economics_workflow_is_retired(self):
        workflow = MODULE_PATH.parents[1] / ".github/workflows/hrrr-executable-economics.yml"
        self.assertFalse(workflow.exists())

    def test_parent_gate_accepts_only_complete_passing_oos(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_path, capture_path, report = passing_artifacts(Path(temporary))
            _, rows, models = economics.verify_oos_artifact(report_path, capture_path)
            self.assertEqual(len(rows), 5000)
            self.assertEqual(len(models), 80)
            failed = copy.deepcopy(report)
            failed["evaluation"]["diagnostic_decision"]["gates"]["every_station_holdout_passes"] = False
            failed["evaluation"]["diagnostic_decision"]["passes"] = False
            report_path.write_text(json.dumps(failed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "did not pass"):
                economics.verify_oos_artifact(report_path, capture_path)

    def test_failed_parent_gate_prevents_client_construction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path, capture_path, report = passing_artifacts(root)
            report["design"]["mode"] = "development"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            constructed = []
            def forbidden_client(*args):
                constructed.append(args)
                raise AssertionError("network client must not be constructed")
            with self.assertRaisesRegex(ValueError, "did not pass"):
                economics.run_audit(report_path, capture_path, root / "out", economics.NETWORK_LIMIT, forbidden_client)
            self.assertEqual(constructed, [])

    def test_price_fee_edge_boundaries_are_exact(self):
        for price in (Decimal("0.70"), Decimal("0.97")):
            exact_score = price + economics.fee(price) + economics.MIN_EDGE
            self.assertTrue(economics.quote_is_eligible(price, exact_score))
            self.assertFalse(economics.quote_is_eligible(price, exact_score - Decimal("0.00000001")))
        self.assertFalse(economics.quote_is_eligible(Decimal("0.6999"), Decimal("1")))
        self.assertFalse(economics.quote_is_eligible(Decimal("0.9701"), Decimal("1")))

    def test_candle_uses_historical_close_and_rejects_live_only_field(self):
        candidate = {
            "station_id": "KATL", "market_date": "2024-03-16", "market_ticker": "TICKER",
            "score": "0.950000", "outcome_no": 1,
        }
        instant = int(economics.decision_clock(date(2024, 3, 16)).timestamp())
        historical = self.FakeClient({
            "ticker": "TICKER",
            "candlesticks": [{"end_period_ts": instant, "yes_bid": {"close": "0.20"}}],
        })
        result = economics.capture_quote(historical, "KXHIGHTATL", candidate)
        self.assertTrue(result["candidate"])
        self.assertEqual(result["no_price_proxy"], "0.80")

        live_schema = self.FakeClient({
            "ticker": "TICKER",
            "candlesticks": [{"end_period_ts": instant, "yes_bid": {"close_dollars": "0.20"}}],
        })
        result = economics.capture_quote(live_schema, "KXHIGHTATL", candidate)
        self.assertFalse(result["candidate"])
        self.assertEqual(result["reason"], "missing_historical_yes_bid_close")

    def test_trade_proxy_excludes_blocks_and_requires_explicit_nonblock_identity(self):
        selection = {
            "station_id": "KATL", "market_date": "2024-03-16", "market_ticker": "TICKER",
            "decision_at": "2024-03-15T20:05:00Z", "no_price_proxy": "0.80",
        }
        trade = {
            "ticker": "TICKER", "trade_id": "trade-1", "created_time": "2024-03-15T20:06:00Z",
            "taker_outcome_side": "no", "count_fp": "1.00", "no_price_dollars": "0.79",
            "is_block_trade": False,
        }
        client = self.FakeClient({"trades": [trade], "cursor": ""})
        result = economics.fetch_trade_proxy(client, selection, "2026-06-30T00:00:00Z")
        self.assertEqual(result["trade_id"], "trade-1")
        self.assertEqual(result["trade_no_price"], "0.79")
        self.assertIn("is_block_trade=false", client.urls[0])

        for invalid in (True, None):
            malformed = copy.deepcopy(trade)
            if invalid is None:
                malformed.pop("is_block_trade")
            else:
                malformed["is_block_trade"] = invalid
            client = self.FakeClient({"trades": [malformed], "cursor": ""})
            with self.assertRaisesRegex(ValueError, "block identity"):
                economics.fetch_trade_proxy(client, selection, "2026-06-30T00:00:00Z")

    def test_supported_submission_uses_frozen_limit_not_better_trade_price(self):
        winning = {"no_price_proxy": "0.80", "outcome_no": 1}
        proxy = {"trade_no_price": "0.70"}
        self.assertEqual(
            economics.supported_submission_return(winning, proxy),
            Decimal("1") - Decimal("0.80") - economics.fee(Decimal("0.80")),
        )
        losing = {"no_price_proxy": "0.80", "outcome_no": 0}
        self.assertEqual(
            economics.supported_submission_return(losing, proxy),
            -Decimal("0.80") - economics.fee(Decimal("0.80")),
        )
        self.assertEqual(economics.supported_submission_return(winning, None), Decimal("0"))

    def test_contract_scoring_floors_continuous_distance_conservatively(self):
        source = {"station_id": "KATL", "market_date": "2024-03-16", "forecast_high_f": "90.4", "observed_high_f": "94"}
        market = {"ticker": "T", "event_ticker": "KXHIGHTATL-24MAR16", "market_type": "binary", "strike_type": "greater", "floor_strike": 94, "cap_strike": None, "result": "no", "yes_sub_title": "95° or above", "is_provisional": False}
        models = {("KATL", distance): Decimal("0.91") + Decimal(distance - 4) / 100 for distance in economics.DISTANCES}
        result = economics.score_contract(source, market, models)
        self.assertEqual(result["distance_f"], "4.1")
        self.assertEqual(result["score_distance_bucket_f"], 4)
        self.assertEqual(result["score"], "0.91")
        source["forecast_high_f"] = "90.5001"
        self.assertIsNone(economics.score_contract(source, market, models))

    def test_initial_economics_can_pass_without_claiming_scale_or_fills(self):
        rows = []
        start = date(2024, 1, 1)
        stations = list(economics.STATION_SERIES)[:10]
        for index in range(100):
            win = index % 11 != 10
            price = Decimal("0.70")
            exact_fee = economics.fee(price)
            rows.append({
                "market_date": (start + timedelta(days=index)).isoformat(), "station_id": stations[index % 10],
                "score": "0.910000", "outcome_no": int(win), "no_price_proxy": str(price),
                "public_trade_proxy": {"no_price": str(price), "fee": str(exact_fee)},
                "submission_return": str(Decimal(1) - price - exact_fee if win else -price - exact_fee),
            })
        result = economics.evaluate_selections(rows)
        self.assertTrue(result["initial_economic_evidence_passes"])
        self.assertFalse(result["scale_research_evidence_passes"])
        self.assertFalse(result["provider_confirmed_fill_evidence"])
        self.assertFalse(result["production_activation"])


if __name__ == "__main__":
    unittest.main()
