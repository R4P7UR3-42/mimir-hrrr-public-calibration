#!/usr/bin/env python3
"""Frozen common-market launch-window audit for the daily-low model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
prior = load_module("low_temperature_economics", Path(__file__).with_name("evaluate_hrrr_low_temperature_economics.py"))
WINDOW = ("2026-04-03", "2026-07-23", 112, "launch-window-v1")
SCHEMA = "hrrr_v4_low_temperature_wilson90_launch_executable_economics_v1"
PREDECLARATION_SHA256 = "dbc3231320b13240fd2e42fc5047c58a446247c28ba8ce624d518dc28e5fc163"
INVENTORY_REPORT_SHA256 = "41f2c19984ec09c50eebc0fd4da3906333314d69988a2ea1f8f29a5751d0e1c9"
NETWORK_LIMIT = 10_000
MINIMUM_COMPLETE_DATES = 110


class CachedPublicClient(prior.econ.PublicClient):
    def __init__(self, output_dir: Path, maximum: int, cache_root: Path):
        prior.econ.NETWORK_LIMIT = NETWORK_LIMIT
        super().__init__(output_dir, maximum)
        self.cache_hits = 0
        self.cached: dict[str, tuple[bytes, str]] = {}
        for request_path in sorted((cache_root / "raw").glob("*.request.json")):
            request = json.loads(request_path.read_text())
            url = request.get("request_url")
            body_path = request_path.with_name(request_path.name.removesuffix(".request.json") + ".json")
            if not isinstance(url, str) or not body_path.is_file() or url in self.cached:
                raise ValueError("Sealed provider inventory cache is malformed or duplicated")
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != request.get("response_sha256"):
                raise ValueError("Sealed provider inventory cache checksum drifted")
            self.cached[url] = (body, body_path.name)

    def fetch(self, url: str, label: str) -> dict:
        cached = self.cached.get(url)
        if cached is None:
            return super().fetch(url, label)
        body, source_name = cached
        self.cache_hits += 1
        prior.econ.create_once(self.output_dir / "raw" / f"{label}.json", body)
        prior.econ.atomic_json(self.output_dir / "raw" / f"{label}.request.json", {
            "request_url": url, "response_sha256": hashlib.sha256(body).hexdigest(),
            "cache_hit": True, "sealed_source_name": source_name,
        })
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError(f"Cached provider payload is not an object for {label}")
        return payload


def verify_inventory_cache(cache_root: Path) -> None:
    report = cache_root / "report.json"
    if prior.econ.file_sha256(report) != INVENTORY_REPORT_SHA256:
        raise ValueError("Sealed zero-support inventory report checksum is invalid")
    payload = json.loads(report.read_text())
    if (
        payload.get("schema") != prior.SCHEMA
        or payload.get("network_policy", {}).get("actual_requests") != 95
        or payload.get("support_funnel", {}).get("matched_events") != 0
        or payload.get("support_funnel", {}).get("scored_contracts") != 0
        or payload.get("support_funnel", {}).get("eligible_quotes") != 0
        or payload.get("active_trading_capability_changed") is not False
    ):
        raise ValueError("Sealed zero-support inventory identity is invalid")


def load_window(capture_root: Path, output_dir: Path) -> tuple[list[dict], dict]:
    prior.low.EVALUATION = WINDOW
    stations, identity = prior.low.base.load_parent_identity(capture_root, WINDOW)
    model, model_map, _ = prior.low.load_frozen_model(stations)
    forecasts = prior.low.base.load_forecast_minima(capture_root, WINDOW)
    body, url = prior.low.base.fetch_outcomes(identity, WINDOW)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation-tmin.json").write_bytes(body)
    outcomes, exclusions, complete = prior.low.parse_whole_dates(body, identity)
    if len(complete) < MINIMUM_COMPLETE_DATES:
        raise ValueError("Launch-window complete-date floor failed")
    rows = prior.low.base.join_residuals(
        [row for row in forecasts if row["market_date"] in set(complete)], outcomes
    )
    return rows, {
        "candidate_dates": WINDOW[2], "complete_dates": len(complete), "excluded_dates": exclusions,
        "tmin_url": url, "tmin_sha256": hashlib.sha256(body).hexdigest(), "model": model,
    }


def terminal_scalar_exclusion(source: dict, event_ticker: str, market: dict) -> dict | None:
    if market.get("result") != "scalar":
        return None
    return {
        "station_id": source["station_id"], "market_date": source["market_date"],
        "event_ticker": event_ticker, "market_ticker": market.get("ticker"),
        "status": market.get("status"), "result": "scalar",
        "settlement_ts": market.get("settlement_ts"),
        "reason": "terminal_scalar_is_not_binary_outcome_evidence",
    }


def run(capture_root: Path, cache_root: Path, output_dir: Path, maximum: int) -> dict:
    if prior.econ.file_sha256(ROOT / "LOW_TEMPERATURE_LAUNCH_ECONOMICS_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Launch-window predeclaration checksum is invalid")
    if maximum != NETWORK_LIMIT:
        raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
    verify_inventory_cache(cache_root)
    prior.econ.assert_not_production_host()
    rows, weather = load_window(capture_root, output_dir)
    client = CachedPublicClient(output_dir, maximum, cache_root)
    prior.low.EVALUATION = WINDOW
    events, markets, fees = prior.load_provider_inventory(client)
    cutoffs = prior.econ.historical_cutoffs(client)
    quote_rows, bridge_rows, scalar_exclusions, by_date = [], [], [], defaultdict(list)
    funnel = {
        "complete_station_dates": len(rows), "matched_events": 0,
        "scalar_settlement_exclusions": 0, "scored_contracts": 0, "eligible_quotes": 0,
    }
    model_map = {
        (row["station_id"], row["distance_f"]): prior.econ.decimal(row["wilson90_lower_score"], "score")
        for row in weather["model"]["station_models"]
    }
    for source in rows:
        series = prior.STATION_SERIES[source["station_id"]]
        event_ticker = prior.exact_event_ticker(series, source["market_date"])
        event = events.get(event_ticker)
        if event is None:
            continue
        supported, source_kind = prior.source_supported(source["station_id"], event.get("settlement_sources"))
        lower = [market for market in markets.get(event_ticker, []) if market.get("strike_type") == "less"]
        if len(lower) != 1:
            raise ValueError(f"Launch event lacks exactly one lower outer contract: {event_ticker}")
        scalar_exclusion = terminal_scalar_exclusion(source, event_ticker, lower[0])
        if scalar_exclusion is not None:
            scalar_exclusions.append(scalar_exclusion)
            funnel["scalar_settlement_exclusions"] += 1
            continue
        funnel["matched_events"] += 1
        candidate = prior.score_lower_contract(source, lower[0], model_map)
        if candidate is None:
            continue
        candidate.update({
            "event_settlement_source_supported": supported,
            "event_settlement_source_kind": source_kind,
            "event_settlement_sources": event.get("settlement_sources"),
        })
        bridge_rows.append(candidate)
        funnel["scored_contracts"] += 1
        quoted = prior.econ.capture_quote(client, series, candidate)
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
    for market_date in prior.low.base.iso_dates(WINDOW[0], WINDOW[1]):
        candidates = by_date[market_date]
        if not candidates:
            continue
        candidates.sort(key=lambda row: (-prior.econ.decimal(row["conservative_edge"], "edge"), prior.econ.decimal(row["no_price_proxy"], "price"), -prior.econ.decimal(row["score"], "score"), row["market_ticker"]))
        selected = candidates[0]
        proxy = prior.econ.fetch_trade_proxy(client, selected, cutoffs["trades_created_ts"])
        selected["public_trade_proxy"] = proxy
        selected["submission_return"] = str(prior.econ.supported_submission_return(selected, proxy))
        selections.append(selected)
    prior.econ.BANDS = prior.BANDS
    evaluation = prior.econ.evaluate_selections(selections)
    evaluation["settlement_bridge_gates"] = bridge_gates
    evaluation["settlement_bridge_passes"] = all(bridge_gates.values())
    evaluation["initial_economic_evidence_passes"] = evaluation["initial_economic_evidence_passes"] and all(bridge_gates.values())
    evaluation["scale_research_evidence_passes"] = False
    evaluation["scale_unavailable_reason"] = "frozen_launch_window_has_112_dates_not_250"
    report = {
        "schema": SCHEMA, "predeclaration_sha256": PREDECLARATION_SHA256,
        "sealed_inventory_report_sha256": INVENTORY_REPORT_SHA256,
        "research_only": True, "historical_price_data_inspected": True, "historical_depth_known": False,
        "public_trade_proxy_is_provider_confirmed_fill": False, "capital_risk_authority": False,
        "production_activation": False, "active_trading_capability_changed": False, "automatic_production_activation": False,
        "window_weather": weather,
        "network_policy": {"maximum_new_economics_requests": NETWORK_LIMIT, "actual_new_economics_requests": client.used, "inventory_cache_hits": client.cache_hits, "ncei_requests": 1, "no_retry": True, "stop_on_http_429": True},
        "fee_identities": fees, "historical_cutoffs": cutoffs, "support_funnel": funnel,
        "scalar_settlement_exclusions": scalar_exclusions,
        "settlement_bridge_rows": bridge_rows, "quote_rows": quote_rows, "evaluation": evaluation,
    }
    prior.econ.atomic_json(output_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--inventory-cache-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, required=True)
    args = parser.parse_args()
    report = run(args.capture_root, args.inventory_cache_root, args.output_dir.resolve(), args.max_requests)
    print(json.dumps({
        "settlement_bridge_passes": report["evaluation"]["settlement_bridge_passes"],
        "initial_economic_evidence_passes": report["evaluation"]["initial_economic_evidence_passes"],
        "new_requests": report["network_policy"]["actual_new_economics_requests"],
        "cache_hits": report["network_policy"]["inventory_cache_hits"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
