import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("evaluate_hrrr_low_temperature_economics.py")
SPEC = importlib.util.spec_from_file_location("low_temperature_economics", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class LowTemperatureEconomicsTest(unittest.TestCase):
    def market(self, cap="60", result="no"):
        return {
            "ticker": "KXLOWTNYC-25JAN01-T59",
            "event_ticker": "KXLOWTNYC-25JAN01",
            "market_type": "binary",
            "strike_type": "less",
            "floor_strike": None,
            "cap_strike": cap,
            "result": result,
            "is_provisional": False,
            "mve_collection_ticker": None,
        }

    def test_exact_distance_boundaries_and_settlement_bridge(self):
        models = {("KNYC", distance): Decimal("0.95") for distance in (4, 5, 6, 7)}
        source = {"station_id": "KNYC", "market_date": "2025-01-01", "forecast_min_f": Decimal("63.5"), "observed_min_f": Decimal("60")}
        exact = audit.score_lower_contract(source, self.market(), models)
        self.assertEqual(exact["distance_f"], "4.0")
        self.assertEqual(exact["outcome_no"], 1)
        self.assertTrue(exact["settlement_matches_ncei"])
        source["forecast_min_f"] = Decimal("63.4999")
        self.assertIsNone(audit.score_lower_contract(source, self.market(), models))
        source["forecast_min_f"] = Decimal("67.5")
        self.assertIsNone(audit.score_lower_contract(source, self.market(), models))

    def test_provider_result_mismatch_is_explicit(self):
        models = {("KNYC", distance): Decimal("0.95") for distance in (4, 5, 6, 7)}
        source = {"station_id": "KNYC", "market_date": "2025-01-01", "forecast_min_f": Decimal("63.5"), "observed_min_f": Decimal("60")}
        row = audit.score_lower_contract(source, self.market(result="yes"), models)
        self.assertFalse(row["settlement_matches_ncei"])

    def test_exact_supported_settlement_sources(self):
        self.assertEqual(audit.source_supported("KNYC", [audit.TWC_SOURCE]), (True, "weather_company_kalshi"))
        nws = [{"name": "NWS Climatological Report", "url": "https://forecast.weather.gov/product.php?site=OKX&product=CLI&issuedby=NYC"}]
        self.assertEqual(audit.source_supported("KNYC", nws), (True, "exact_nws_cli"))
        wrong = [{"name": "NWS Climatological Report", "url": "https://forecast.weather.gov/product.php?site=OKX&product=CLI&issuedby=LGA"}]
        self.assertEqual(audit.source_supported("KNYC", wrong)[0], False)
        self.assertEqual(audit.source_supported("KNYC", [audit.TWC_SOURCE, audit.TWC_SOURCE])[0], False)

    def test_parent_verifies_without_network(self):
        capture = Path("/var/tmp/mimir-hrrr-later-failed-33300096256/artifact/capture")
        if capture.exists():
            rows, models = audit.verify_parent(capture)
            self.assertEqual(len(rows), 5000)
            self.assertEqual(len(models), 80)

    def test_public_workflow_is_isolated_and_one_shot(self):
        workflow = MODULE_PATH.parents[1] / ".github/workflows/hrrr-low-temperature-economics.yml"
        self.assertFalse(workflow.exists(), "consumed zero-support workflow must remain retired")


if __name__ == "__main__":
    unittest.main()
