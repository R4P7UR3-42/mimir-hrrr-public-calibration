#!/usr/bin/env python3
"""Frozen settlement and executable-economics audit for the daily-low successor."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import urllib.parse
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Callable


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
econ = load_module("low_temperature_economics_base", Path(__file__).with_name("evaluate_hrrr_executable_economics.py"))
low = load_module("low_temperature_wilson90", Path(__file__).with_name("evaluate_hrrr_low_temperature_wilson90.py"))

SCHEMA = "hrrr_v4_low_temperature_wilson90_executable_economics_v1"
PREDECLARATION_SHA256 = "b6e4a8986d6403d5288e28c9e6065a522f6d164b53f9c5bd629a94277033715c"
PARENT_REPORT_SHA256 = "1e43d4806dca12721a99fa1787c278a729d055f4464e7aeb3196c53bc8bd2bb4"
PARENT_TMIN_SHA256 = "dccb0fd65c41fd610eac7c4f9ee7c20cbe78f9beafa0e07b1540dfc5759ada7a"
NETWORK_LIMIT = 15_000
EVENT_PAGE_LIMIT = 200
MARKET_PAGE_LIMIT = 1_000
BASE_URL = econ.BASE_URL
TWC_SOURCE = {"name": "The Weather Company", "url": "https://weather.com/kalshi"}
BANDS = (
    ("0.900_0.925", Decimal("0.900"), Decimal("0.925")),
    ("0.925_1.000", Decimal("0.925"), Decimal("1.000001")),
)
STATION_SERIES = {
    "KATL": "KXLOWTATL", "KAUS": "KXLOWTAUS", "KBOS": "KXLOWTBOS", "KDCA": "KXLOWTDC",
    "KDEN": "KXLOWTDEN", "KDFW": "KXLOWTDAL", "KHOU": "KXLOWTHOU", "KLAS": "KXLOWTLV",
    "KLAX": "KXLOWTLAX", "KMDW": "KXLOWTCHI", "KMIA": "KXLOWTMIA", "KMSP": "KXLOWTMIN",
    "KMSY": "KXLOWTNOLA", "KNYC": "KXLOWTNYC", "KOKC": "KXLOWTOKC", "KPHL": "KXLOWTPHIL",
    "KPHX": "KXLOWTPHX", "KSAT": "KXLOWTSATX", "KSEA": "KXLOWTSEA", "KSFO": "KXLOWTSFO",
}
ISSUEDBY = {
    "KATL": "ATL", "KAUS": "AUS", "KBOS": "BOS", "KDCA": "DCA", "KDEN": "DEN", "KDFW": "DFW",
    "KHOU": "HOU", "KLAS": "LAS", "KLAX": "LAX", "KMDW": "MDW", "KMIA": "MIA", "KMSP": "MSP",
    "KMSY": "MSY", "KNYC": "NYC", "KOKC": "OKC", "KPHL": "PHL", "KPHX": "PHX", "KSAT": "SAT",
    "KSEA": "SEA", "KSFO": "SFO",
}


def result_root() -> Path:
    return ROOT / "data/results/hrrr-v4-low-temperature-wilson90-v1"


def verify_parent(capture_root: Path) -> tuple[list[dict], dict[tuple[str, int], Decimal]]:
    report_path, tmin_path = result_root() / "evaluation.json", result_root() / "evaluation-tmin.json"
    if econ.file_sha256(report_path) != PARENT_REPORT_SHA256 or econ.file_sha256(tmin_path) != PARENT_TMIN_SHA256:
        raise ValueError("Frozen low-temperature parent checksum is invalid")
    report = json.loads(report_path.read_text())
    decision = report.get("evaluation", {}).get("diagnostic_decision", {})
    if (
        report.get("schema") != low.EVALUATION_SCHEMA
        or report.get("design", {}).get("model") != low.MODEL
        or decision.get("passes") is not True
        or not isinstance(decision.get("gates"), dict)
        or any(value is not True for value in decision["gates"].values())
        or report.get("active_trading_capability_changed") is not False
        or report.get("automatic_production_activation") is not False
    ):
        raise ValueError("Frozen low-temperature parent did not pass every exact gate")
    stations, identity = low.base.load_parent_identity(capture_root, low.EVALUATION)
    model, model_map, _ = low.load_frozen_model(stations)
    if model != report.get("model_artifact"):
        raise ValueError("Frozen low-temperature parent model drifted")
    outcomes, exclusions, complete = low.parse_whole_dates(tmin_path.read_bytes(), identity)
    if exclusions or len(complete) != 250:
        raise ValueError("Frozen low-temperature parent outcome coverage drifted")
    forecasts = low.base.load_forecast_minima(capture_root, low.EVALUATION)
    rows = low.base.join_residuals(forecasts, outcomes)
    if len(rows) != 5_000:
        raise ValueError("Frozen low-temperature station/date grid is incomplete")
    return rows, model_map


def exact_event_ticker(series: str, market_date: str) -> str:
    parsed = dt.date.fromisoformat(market_date)
    return f"{series}-{parsed.year % 100:02d}{econ.MONTHS[parsed.month]}{parsed.day:02d}"


def source_supported(station: str, sources: object) -> tuple[bool, str]:
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
        return False, "ambiguous_event_settlement_source"
    source = sources[0]
    if source == TWC_SOURCE:
        return True, "weather_company_kalshi"
    url = source.get("url")
    if source.get("name") == "NWS Climatological Report" and isinstance(url, str):
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if (
            parsed.scheme == "https"
            and parsed.netloc == "forecast.weather.gov"
            and query.get("product") == ["CLI"]
            and query.get("issuedby") == [ISSUEDBY[station]]
        ):
            return True, "exact_nws_cli"
    return False, "unsupported_event_settlement_source"


def validate_series(client, series: str) -> dict:
    payload = client.fetch(f"{BASE_URL}/series/{series}", f"{series}-series")
    row = payload.get("series")
    if (
        not isinstance(row, dict)
        or row.get("ticker") != series
        or row.get("category") != "Climate and Weather"
        or row.get("fee_type") != "quadratic"
        or row.get("fee_multiplier") != 1
        or row.get("settlement_sources") != [TWC_SOURCE]
    ):
        raise ValueError(f"Current low-temperature series identity is invalid for {series}")
    changes = client.fetch(
        f"{BASE_URL}/series/fee_changes?" + urllib.parse.urlencode({"series_ticker": series, "show_historical": "true"}),
        f"{series}-fee-changes",
    )
    if changes != {"series_fee_change_arr": []}:
        raise ValueError(f"Fee history is not the unchanged baseline for {series}")
    return {"series_ticker": series, "fee_type": "quadratic", "multiplier": 1, "current_settlement_source": TWC_SOURCE}


def paginated(client, path: str, fixed: dict[str, str], key: str, label: str, limit: int) -> list[dict]:
    cursor, page, rows = "", 0, []
    while True:
        query = {**fixed, "limit": str(limit)}
        if cursor:
            query["cursor"] = cursor
        payload = client.fetch(f"{BASE_URL}/{path}?" + urllib.parse.urlencode(query), f"{label}-p{page:03d}")
        values, next_cursor = payload.get(key), payload.get("cursor")
        if not isinstance(values, list) or not all(isinstance(row, dict) for row in values) or not isinstance(next_cursor, str):
            raise ValueError(f"Paginated {key} response is malformed for {label}")
        rows.extend(values)
        if not next_cursor:
            return rows
        if next_cursor == cursor:
            raise ValueError(f"Paginated {key} cursor repeated for {label}")
        cursor, page = next_cursor, page + 1


def is_finalized_historical_market(market: dict) -> bool:
    """Require the exact terminal REST identity returned for settled markets."""
    ticker = market.get("ticker")
    settlement_ts = market.get("settlement_ts")
    return (
        isinstance(ticker, str)
        and bool(ticker)
        and market.get("status") == "finalized"
        and market.get("result") in ("yes", "no", "scalar")
        and isinstance(settlement_ts, str)
        and bool(settlement_ts)
    )


def load_provider_inventory(client) -> tuple[dict[str, dict], dict[str, list[dict]], list[dict]]:
    events: dict[str, dict] = {}
    markets: dict[str, list[dict]] = defaultdict(list)
    fees = []
    expected_events = {
        exact_event_ticker(series, market_date)
        for series in STATION_SERIES.values()
        for market_date in low.base.iso_dates(low.EVALUATION[0], low.EVALUATION[1])
    }
    for series in sorted(STATION_SERIES.values()):
        fees.append(validate_series(client, series))
        event_rows = paginated(client, "events", {"series_ticker": series, "status": "settled"}, "events", f"{series}-events", EVENT_PAGE_LIMIT)
        for event in event_rows:
            ticker = event.get("event_ticker")
            if ticker in expected_events:
                if ticker in events or event.get("series_ticker") != series:
                    raise ValueError(f"Historical event identity is duplicated for {ticker}")
                events[ticker] = event
        market_rows = paginated(client, "historical/markets", {"series_ticker": series}, "markets", f"{series}-markets", MARKET_PAGE_LIMIT)
        for market in market_rows:
            event = market.get("event_ticker")
            if event in expected_events:
                if not is_finalized_historical_market(market):
                    raise ValueError(f"Historical market identity is malformed for {event}")
                markets[event].append(market)
    return events, markets, fees


def score_lower_contract(source: dict, market: dict, model_map: dict[tuple[str, int], Decimal]) -> dict | None:
    if market.get("strike_type") != "less":
        return None
    cap = econ.decimal(market.get("cap_strike"), "cap strike")
    forecast, observed = source["forecast_min_f"], source["observed_min_f"]
    distance = forecast - cap + Decimal("0.5")
    if not Decimal("4.0") <= distance < Decimal("8.0"):
        return None
    bucket = int(distance.to_integral_value(rounding=ROUND_FLOOR))
    score = model_map[(source["station_id"], bucket)]
    if score < low.base.SCORE_FLOOR:
        return None
    ticker = market.get("ticker")
    ncei_no, provider_no = observed >= cap, market.get("result") == "no"
    if (
        cap != cap.to_integral_value()
        or market.get("market_type") != "binary"
        or market.get("floor_strike") is not None
        or market.get("result") not in ("yes", "no")
        or not isinstance(ticker, str)
        or market.get("is_provisional") is True
        or market.get("mve_collection_ticker") not in (None, "")
    ):
        raise ValueError(f"Exact lower-outer market identity is invalid for {ticker}")
    return {
        "station_id": source["station_id"], "market_date": source["market_date"],
        "forecast_min_f": str(forecast), "observed_min_f": str(observed),
        "event_ticker": market["event_ticker"], "market_ticker": ticker, "cap_strike": str(cap),
        "distance_f": str(distance), "score_distance_bucket_f": bucket, "score": str(score),
        "outcome_no": int(provider_no), "ncei_outcome_no": int(ncei_no), "settlement_matches_ncei": provider_no == ncei_no,
    }


def run(capture_root: Path, output_dir: Path, maximum: int, client_factory: Callable = econ.PublicClient) -> dict:
    if econ.file_sha256(ROOT / "LOW_TEMPERATURE_ECONOMICS_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Frozen low-temperature economics predeclaration checksum is invalid")
    rows, model_map = verify_parent(capture_root)
    if maximum != NETWORK_LIMIT:
        raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
    econ.assert_not_production_host()
    econ.NETWORK_LIMIT = NETWORK_LIMIT
    client = client_factory(output_dir, maximum)
    events, markets, fees = load_provider_inventory(client)
    cutoffs = econ.historical_cutoffs(client)
    quote_rows, by_date, bridge_rows = [], defaultdict(list), []
    funnel = {"parent_station_dates": len(rows), "matched_events": 0, "scored_contracts": 0, "eligible_quotes": 0}
    for source in rows:
        series = STATION_SERIES[source["station_id"]]
        event_ticker = exact_event_ticker(series, source["market_date"])
        event = events.get(event_ticker)
        if event is None:
            continue
        supported, source_kind = source_supported(source["station_id"], event.get("settlement_sources"))
        funnel["matched_events"] += 1
        lower = [market for market in markets.get(event_ticker, []) if market.get("strike_type") == "less"]
        if len(lower) != 1:
            raise ValueError(f"Event does not contain exactly one lower outer contract: {event_ticker}")
        candidate = score_lower_contract(source, lower[0], model_map)
        if candidate is None:
            continue
        candidate["event_settlement_source_supported"] = supported
        candidate["event_settlement_source_kind"] = source_kind
        candidate["event_settlement_sources"] = event.get("settlement_sources")
        bridge_rows.append(candidate)
        funnel["scored_contracts"] += 1
        quoted = econ.capture_quote(client, series, candidate)
        quote_rows.append(quoted)
        if quoted["candidate"] is True:
            funnel["eligible_quotes"] += 1
            by_date[quoted["market_date"]].append(quoted)
    bridge_dates = {row["market_date"] for row in bridge_rows}
    bridge_stations = {row["station_id"] for row in bridge_rows}
    bridge_gates = {
        "at_least_100_scored_dates": len(bridge_dates) >= 100,
        "at_least_8_scored_stations": len(bridge_stations) >= 8,
        "every_event_source_supported": bool(bridge_rows) and all(row["event_settlement_source_supported"] for row in bridge_rows),
        "zero_provider_ncei_settlement_mismatches": bool(bridge_rows) and all(row["settlement_matches_ncei"] for row in bridge_rows),
    }
    selections = []
    for market_date in low.base.iso_dates(low.EVALUATION[0], low.EVALUATION[1]):
        candidates = by_date[market_date]
        if not candidates:
            continue
        candidates.sort(key=lambda row: (-econ.decimal(row["conservative_edge"], "edge"), econ.decimal(row["no_price_proxy"], "price"), -econ.decimal(row["score"], "score"), row["market_ticker"]))
        selected = candidates[0]
        proxy = econ.fetch_trade_proxy(client, selected, cutoffs["trades_created_ts"])
        selected["public_trade_proxy"] = proxy
        selected["submission_return"] = str(econ.supported_submission_return(selected, proxy))
        selections.append(selected)
    econ.BANDS = BANDS
    evaluation = econ.evaluate_selections(selections)
    evaluation["settlement_bridge_gates"] = bridge_gates
    evaluation["settlement_bridge_passes"] = all(bridge_gates.values())
    evaluation["initial_economic_evidence_passes"] = evaluation["initial_economic_evidence_passes"] and all(bridge_gates.values())
    evaluation["scale_research_evidence_passes"] = evaluation["scale_research_evidence_passes"] and all(bridge_gates.values())
    report = {
        "schema": SCHEMA, "predeclaration_sha256": PREDECLARATION_SHA256,
        "parent_report_sha256": PARENT_REPORT_SHA256, "parent_tmin_sha256": PARENT_TMIN_SHA256,
        "research_only": True, "historical_price_data_inspected": True, "historical_depth_known": False,
        "public_trade_proxy_is_provider_confirmed_fill": False, "capital_risk_authority": False,
        "production_activation": False, "active_trading_capability_changed": False, "automatic_production_activation": False,
        "network_policy": {"maximum_requests": NETWORK_LIMIT, "actual_requests": client.used, "maximum_starts_per_second": 4, "no_retry": True, "stop_on_http_429": True},
        "fee_identities": fees, "historical_cutoffs": cutoffs, "support_funnel": funnel,
        "settlement_bridge_rows": bridge_rows, "quote_rows": quote_rows, "evaluation": evaluation,
    }
    econ.atomic_json(output_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-requests", type=int)
    args = parser.parse_args()
    if args.verify_only:
        rows, models = verify_parent(args.capture_root)
        print(json.dumps({"parent_passes": True, "rows": len(rows), "models": len(models)}, sort_keys=True))
        return
    if args.output_dir is None or args.max_requests is None:
        raise ValueError("Network audit requires output directory and exact request ceiling")
    report = run(args.capture_root, args.output_dir.resolve(), args.max_requests)
    print(json.dumps({
        "settlement_bridge_passes": report["evaluation"]["settlement_bridge_passes"],
        "initial_economic_evidence_passes": report["evaluation"]["initial_economic_evidence_passes"],
        "scale_research_evidence_passes": report["evaluation"]["scale_research_evidence_passes"],
        "network_requests": report["network_policy"]["actual_requests"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
