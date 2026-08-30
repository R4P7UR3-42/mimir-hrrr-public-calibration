#!/usr/bin/env python3
"""Hard-gated public executable-economics audit for the frozen HRRR OOS successor."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, getcontext
from pathlib import Path
from typing import Callable

getcontext().prec = 40

OOS_RUN_ID = "33291428414"
OOS_HEAD_SHA = "d313b7bd86b2bc7e59de0411d2625d4191412895"
OOS_SCHEMA = "hrrr_v4_conservative_station_jeffreys_evaluation_v1"
CAPTURE_SCHEMA = "hrrr_v4_archive_calibration_capture_v1"
MODEL = "hrrr_v4_station_jeffreys_minus_0035_v1"
REPORT_SCHEMA = "hrrr_v4_conservative_executable_economics_v1"
START, END, DATE_COUNT = dt.date(2024, 3, 16), dt.date(2024, 11, 20), 250
DISTANCES = (4, 5, 6, 7)
MIN_SCORE = Decimal("0.900")
MIN_PRICE, MAX_PRICE, MIN_EDGE = Decimal("0.70"), Decimal("0.97"), Decimal("0.015")
FEE_RATE, FEE_QUANTUM = Decimal("0.07"), Decimal("0.0001")
NETWORK_LIMIT = 12_000
BOOTSTRAP_SAMPLES = 10_000
LCG_SEED = 0x48525234
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
PREDECLARATION_SHA256 = "bb4dcf53b35677ce182e47d5c86240d5c6458d99e788fc57046e0df82f650aa7"
BANDS = (
    ("0.900_0.925", Decimal("0.900"), Decimal("0.925")),
    ("0.925_0.950", Decimal("0.925"), Decimal("0.950")),
    ("0.950_1.000", Decimal("0.950"), Decimal("1.000")),
)
STATION_SERIES = {
    "KATL": "KXHIGHTATL", "KAUS": "KXHIGHAUS", "KBOS": "KXHIGHTBOS", "KDCA": "KXHIGHTDC",
    "KDEN": "KXHIGHDEN", "KDFW": "KXHIGHTDAL", "KHOU": "KXHIGHTHOU", "KLAS": "KXHIGHTLV",
    "KLAX": "KXHIGHLAX", "KMDW": "KXHIGHCHI", "KMIA": "KXHIGHMIA", "KMSP": "KXHIGHTMIN",
    "KMSY": "KXHIGHTNOLA", "KNYC": "KXHIGHNY", "KOKC": "KXHIGHTOKC", "KPHL": "KXHIGHPHIL",
    "KPHX": "KXHIGHTPHX", "KSAT": "KXHIGHTSATX", "KSEA": "KXHIGHTSEA", "KSFO": "KXHIGHTSFO",
}
MONTHS = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN", 7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def create_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Create-once source changed: {path.name}")
        return
    path.write_bytes(payload)


def decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError(f"{label} is malformed") from error
    if not result.is_finite():
        raise ValueError(f"{label} is non-finite")
    return result


def timestamp(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} is not exact UTC")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is malformed") from error
    if result.tzinfo != dt.timezone.utc:
        raise ValueError(f"{label} is not UTC")
    return result


def date_range(start: dt.date = START, end: dt.date = END) -> list[str]:
    values = []
    current = start
    while current <= end:
        values.append(current.isoformat())
        current += dt.timedelta(days=1)
    return values


def decision_clock(market_date: dt.date) -> dt.datetime:
    return dt.datetime.combine(market_date - dt.timedelta(days=1), dt.time(20, 5), tzinfo=dt.timezone.utc)


def exact_event_ticker(series: str, market_date: dt.date) -> str:
    return f"{series}-{market_date.year % 100:02d}{MONTHS[market_date.month]}{market_date.day:02d}"


def fee(price: Decimal) -> Decimal:
    if price < 0 or price > 1:
        raise ValueError("Fee price is outside [0,1]")
    return (FEE_RATE * price * (Decimal(1) - price)).quantize(FEE_QUANTUM, rounding=ROUND_CEILING)


def quote_is_eligible(price: Decimal, score: Decimal) -> bool:
    return MIN_PRICE <= price <= MAX_PRICE and score - price - fee(price) >= MIN_EDGE


def verify_oos_artifact(report_path: Path, capture_path: Path) -> tuple[dict, list[dict], dict[tuple[str, int], Decimal]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evaluation = report.get("evaluation")
    decision = evaluation.get("diagnostic_decision") if isinstance(evaluation, dict) else None
    design = report.get("design")
    expected_gate_names = {
        "exact_365_training_dates", "exact_250_evaluation_dates", "at_least_100_selected_dates",
        "at_least_8_selected_stations", "positive_brier_skill", "exact_three_reliability_bands",
        "every_reliability_band_ready", "date_clustered_90_margin_nonnegative",
        "date_clustered_95_margin_nonnegative", "station_concentration_at_most_0_35",
        "date_concentration_at_most_0_05", "exact_20_station_holdouts", "every_station_holdout_passes",
    }
    if (
        report.get("schema") != OOS_SCHEMA
        or report.get("research_only") is not True
        or report.get("active_trading_capability_changed") is not False
        or report.get("automatic_production_activation") is not False
        or not isinstance(design, dict)
        or design.get("model") != MODEL
        or design.get("mode") != "oos"
        or design.get("evaluation_start_market_date") != START.isoformat()
        or design.get("evaluation_end_market_date") != END.isoformat()
        or design.get("correction") != "0.035000"
        or design.get("score_floor") != "0.900000"
        or design.get("distances_f") != list(DISTANCES)
        or not isinstance(decision, dict)
        or decision.get("passes") is not True
        or set(decision.get("gates", {})) != expected_gate_names
        or any(value is not True for value in decision["gates"].values())
        or evaluation.get("selected_independent_market_dates", 0) < 100
        or evaluation.get("selected_stations", 0) < 8
    ):
        raise ValueError("Frozen HRRR OOS diagnostic did not pass its exact identity and every gate")
    models = report.get("station_models")
    if not isinstance(models, list) or len(models) != 80:
        raise ValueError("Frozen station model inventory is incomplete")
    model_scores: dict[tuple[str, int], Decimal] = {}
    for row in models:
        key = (row.get("station_id"), row.get("distance_f"))
        if key in model_scores or key[0] not in STATION_SERIES or key[1] not in DISTANCES:
            raise ValueError("Frozen station model identity is malformed")
        score = decimal(row.get("corrected_score"), "corrected score")
        if score < 0 or score >= 1:
            raise ValueError("Frozen station score is outside [0,1)")
        model_scores[key] = score
    if set(model_scores) != {(station, distance) for station in STATION_SERIES for distance in DISTANCES}:
        raise ValueError("Frozen station model grid is incomplete")

    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    rows = capture.get("rows")
    expected_dates = set(date_range())
    identities = set()
    if (
        capture.get("schema") != CAPTURE_SCHEMA
        or capture.get("research_only") is not True
        or capture.get("active_trading_capability_changed") is not False
        or capture.get("automatic_production_activation") is not False
        or capture.get("coverage") != {"independent_market_dates": 250, "complete_station_dates": 5000, "complete": True}
        or not isinstance(rows, list)
        or len(rows) != 5000
    ):
        raise ValueError("Frozen HRRR OOS capture identity is invalid")
    for row in rows:
        identity = (row.get("station_id"), row.get("market_date"))
        if identity in identities:
            raise ValueError("Frozen HRRR OOS capture repeats station/date identity")
        identities.add(identity)
        if (
            identity[0] not in STATION_SERIES
            or identity[1] not in expected_dates
            or row.get("forecast_model") != "hrrr_v4_archive_3km_native_3h_nearest_v1"
            or row.get("forecast_availability_basis") != "hrrr_12z_operational_2000z_upper_bound_v1"
            or row.get("observation_source") != "noaa_ncei_daily_summaries_tmax"
            or timestamp(row.get("forecast_available_at"), "forecast availability").time() != dt.time(20, 0)
        ):
            raise ValueError("Frozen HRRR OOS row identity is invalid")
        decimal(row.get("forecast_high_f"), "forecast high")
        decimal(row.get("observed_high_f"), "observed high")
    if identities != {(station, date) for station in STATION_SERIES for date in expected_dates}:
        raise ValueError("Frozen HRRR OOS capture coverage is incomplete")
    return report, sorted(rows, key=lambda row: (row["market_date"], row["station_id"])), model_scores


def assert_not_production_host() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/status", timeout=1) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError):
        return
    if not isinstance(payload, dict) or payload.get("environment") == "production":
        raise ValueError("HRRR economics acquisition is forbidden on a production Mimir host")


class PublicClient:
    def __init__(self, output_dir: Path, maximum: int):
        if maximum != NETWORK_LIMIT:
            raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
        self.output_dir, self.maximum, self.used, self.last_started = output_dir, maximum, 0, 0.0

    def fetch(self, url: str, label: str) -> dict:
        if self.used >= self.maximum:
            raise ValueError("Frozen network request ceiling exhausted")
        delay = 0.25 - (time.monotonic() - self.last_started)
        if delay > 0:
            time.sleep(delay)
        self.last_started = time.monotonic()
        self.used += 1
        request = urllib.request.Request(url, headers={"User-Agent": "mimir-hrrr-public-economics/1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body, status = response.read(), response.getcode()
                headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as error:
            body = error.read()
            create_once(self.output_dir / "raw" / f"{label}.error-body", body)
            atomic_json(self.output_dir / "raw" / f"{label}.error.json", {
                "request_index": self.used, "request_url": url, "response_status": error.code,
                "response_sha256": sha256(body), "response_headers": dict(error.headers),
            })
            if error.code == 429:
                raise ValueError("Provider acquisition stopped on HTTP 429 without retry") from error
            raise
        create_once(self.output_dir / "raw" / f"{label}.json", body)
        atomic_json(self.output_dir / "raw" / f"{label}.request.json", {
            "request_index": self.used, "request_url": url, "response_status": status, "response_sha256": sha256(body),
        })
        atomic_json(self.output_dir / "raw" / f"{label}.headers.json", headers)
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError(f"Provider payload is not an object for {label}")
        return payload


def validate_fee_identity(client: PublicClient, series: str) -> dict:
    encoded = urllib.parse.quote(series, safe="")
    series_url = f"{BASE_URL}/series/{encoded}"
    baseline = client.fetch(series_url, f"{series}-series").get("series")
    if (
        not isinstance(baseline, dict) or baseline.get("ticker") != series
        or baseline.get("category") != "Climate and Weather"
        or baseline.get("fee_type") != "quadratic" or baseline.get("fee_multiplier") != 1
    ):
        raise ValueError(f"Fee baseline identity is invalid for {series}")
    changes_url = f"{BASE_URL}/series/fee_changes?" + urllib.parse.urlencode({"series_ticker": series, "show_historical": "true"})
    if client.fetch(changes_url, f"{series}-fee-changes") != {"series_fee_change_arr": []}:
        raise ValueError(f"Fee history is not the unchanged baseline for {series}")
    return {"series_ticker": series, "fee_type": "quadratic", "multiplier": "1", "coefficient": "0.07", "quantum": "0.0001", "series_url": series_url, "changes_url": changes_url}


def historical_cutoffs(client: PublicClient) -> dict[str, str]:
    payload = client.fetch(f"{BASE_URL}/historical/cutoff", "historical-cutoff")
    result = {key: str(payload.get(key)) for key in ("market_settled_ts", "trades_created_ts")}
    settled, trades = timestamp(result["market_settled_ts"], "market cutoff"), timestamp(result["trades_created_ts"], "trade cutoff")
    if settled < dt.datetime.combine(END + dt.timedelta(days=2), dt.time(), tzinfo=dt.timezone.utc) or trades <= decision_clock(END) + dt.timedelta(minutes=5):
        raise ValueError("Historical cutoff does not cover the frozen window")
    return result


def event_markets(client: PublicClient, series: str, market_date: dt.date) -> list[dict]:
    event = exact_event_ticker(series, market_date)
    url = f"{BASE_URL}/historical/markets?" + urllib.parse.urlencode({"event_ticker": event, "limit": "1000"})
    payload = client.fetch(url, f"{series}-{market_date.isoformat()}-markets")
    rows = payload.get("markets")
    if not isinstance(rows, list) or payload.get("cursor") not in (None, ""):
        raise ValueError(f"Exact historical event inventory is nonterminal for {event}")
    seen = set()
    for row in rows:
        ticker = row.get("ticker") if isinstance(row, dict) else None
        if not isinstance(ticker, str) or ticker in seen or row.get("event_ticker") != event or not ticker.startswith(event + "-"):
            raise ValueError(f"Exact event identity drifted for {event}")
        seen.add(ticker)
    return rows


def score_contract(source: dict, market: dict, model_scores: dict[tuple[str, int], Decimal]) -> dict | None:
    if market.get("strike_type") != "greater" or market.get("floor_strike") is None:
        return None
    floor = decimal(market["floor_strike"], "floor strike")
    forecast, observed = decimal(source["forecast_high_f"], "forecast high"), decimal(source["observed_high_f"], "observed high")
    distance = floor + Decimal("0.5") - forecast
    if not Decimal("4.0") <= distance < Decimal("8.0"):
        return None
    bucket = int(distance.to_integral_value(rounding=ROUND_FLOOR))
    score = model_scores[(source["station_id"], bucket)]
    if score < MIN_SCORE:
        return None
    outcome_no = observed <= floor
    ticker = market.get("ticker")
    if (
        floor != floor.to_integral_value() or market.get("market_type") != "binary" or market.get("cap_strike") is not None
        or market.get("result") not in ("yes", "no") or (market.get("result") == "no") != outcome_no
        or market.get("yes_sub_title") != f"{int(floor) + 1}° or above"
        or ("is_provisional" in market and market["is_provisional"] is not False)
        or ("mve_collection_ticker" in market and market["mve_collection_ticker"] not in (None, ""))
        or not isinstance(ticker, str)
    ):
        raise ValueError(f"Exact greater-contract identity is invalid for {ticker}")
    return {
        "station_id": source["station_id"], "market_date": source["market_date"], "forecast_high_f": str(forecast),
        "observed_high_f": str(observed), "event_ticker": market["event_ticker"], "market_ticker": ticker,
        "floor_strike": str(floor), "distance_f": str(distance), "score_distance_bucket_f": bucket,
        "score": str(score), "outcome_no": int(outcome_no),
    }


def capture_quote(client: PublicClient, series: str, candidate: dict) -> dict:
    ticker = candidate["market_ticker"]
    clock = decision_clock(dt.date.fromisoformat(candidate["market_date"]))
    instant = int(clock.timestamp())
    path = f"historical/markets/{urllib.parse.quote(ticker, safe='')}/candlesticks"
    url = f"{BASE_URL}/{path}?" + urllib.parse.urlencode({"start_ts": instant, "end_ts": instant, "period_interval": 1})
    payload = client.fetch(url, f"{candidate['station_id']}-{candidate['market_date']}-{ticker}-candle")
    candles = payload.get("candlesticks")
    base = {**candidate, "decision_at": clock.isoformat().replace("+00:00", "Z"), "quote_source_url": url}
    if payload.get("ticker") != ticker or not isinstance(candles, list):
        raise ValueError(f"Candle response identity is invalid for {ticker}")
    if not candles:
        return {**base, "candidate": False, "reason": "empty_candle"}
    if len(candles) != 1 or not isinstance(candles[0], dict) or candles[0].get("end_period_ts") != instant:
        raise ValueError(f"Candle clock identity is invalid for {ticker}")
    yes_bid = candles[0].get("yes_bid")
    if not isinstance(yes_bid, dict) or yes_bid.get("close") is None:
        return {**base, "candidate": False, "reason": "missing_historical_yes_bid_close"}
    bid = decimal(yes_bid["close"], "YES bid")
    if bid <= 0 or bid >= 1:
        return {**base, "candidate": False, "reason": "boundary_yes_bid", "yes_bid": str(bid)}
    price = Decimal(1) - bid
    if price * 100 != (price * 100).to_integral_value():
        raise ValueError(f"NO proxy price is not exact-cent for {ticker}")
    exact_fee, score = fee(price), decimal(candidate["score"], "score")
    edge = score - price - exact_fee
    eligible = quote_is_eligible(price, score)
    return {**base, "candidate": eligible, "reason": "eligible_quote" if eligible else "price_or_edge_outside_policy", "yes_bid": str(bid), "no_price_proxy": str(price), "fee_at_proxy": str(exact_fee), "conservative_edge": f"{edge:.8f}", "historical_depth_known": False}


def fetch_trade_proxy(client: PublicClient, selection: dict, trade_cutoff: str) -> dict | None:
    ticker, start = selection["market_ticker"], timestamp(selection["decision_at"], "decision")
    if start >= timestamp(trade_cutoff, "trade cutoff"):
        raise ValueError("Frozen OOS trade must use the historical partition")
    end = start + dt.timedelta(minutes=5)
    url = f"{BASE_URL}/historical/trades?" + urllib.parse.urlencode({"limit": "1000", "ticker": ticker, "min_ts": int(start.timestamp()), "max_ts": int(end.timestamp()), "is_block_trade": "false"})
    payload = client.fetch(url, f"{selection['station_id']}-{selection['market_date']}-trades")
    trades = payload.get("trades")
    if not isinstance(trades, list) or payload.get("cursor") not in (None, ""):
        raise ValueError(f"Trade response is malformed for {ticker}")
    limit, eligible = decimal(selection["no_price_proxy"], "NO limit"), []
    for trade in trades:
        if not isinstance(trade, dict) or trade.get("ticker") != ticker:
            raise ValueError(f"Trade ticker identity conflicts for {ticker}")
        if trade.get("is_block_trade") is not False:
            raise ValueError(f"Trade block identity is missing or invalid for {ticker}")
        created = timestamp(trade.get("created_time"), "trade time")
        if created < start or created >= end or trade.get("taker_outcome_side") != "no":
            continue
        count, price, trade_id = decimal(trade.get("count_fp"), "trade count"), decimal(trade.get("no_price_dollars"), "trade price"), trade.get("trade_id")
        if isinstance(trade_id, str) and trade_id and count >= 1 and price <= limit:
            eligible.append((created, price, trade_id, count))
    if not eligible:
        return None
    created, price, trade_id, count = sorted(eligible, key=lambda row: (row[0], row[1], row[2]))[0]
    return {"trade_id": trade_id, "created_at": created.isoformat().replace("+00:00", "Z"), "no_price": str(price), "count": str(count), "fee": str(fee(price)), "source_url": url}


def maximum_drawdown(values: list[Decimal]) -> Decimal:
    equity = peak = drawdown = Decimal(0)
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def clustered_lower(rows: list[dict], key: str, tail: Decimal) -> Decimal | None:
    if not rows:
        return None
    groups: dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        groups[row["market_date"]].append(decimal(row[key], key))
    clusters = [groups[name] for name in sorted(groups)]
    state, means = LCG_SEED, []
    for _ in range(BOOTSTRAP_SAMPLES):
        total, count = Decimal(0), 0
        for _ in clusters:
            state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
            values = clusters[(state * len(clusters)) // 0x100000000]
            total += sum(values, Decimal(0)); count += len(values)
        means.append(total / count)
    means.sort()
    return means[math.floor((BOOTSTRAP_SAMPLES - 1) * float(tail))]


def evaluate_selections(selections: list[dict]) -> dict:
    dates, stations = {row["market_date"] for row in selections}, {row["station_id"] for row in selections}
    outcomes = [Decimal(row["outcome_no"]) for row in selections]
    scores = [decimal(row["score"], "score") for row in selections]
    prices = [decimal(row["no_price_proxy"], "price") for row in selections]
    model_brier = sum(((score - outcome) ** 2 for score, outcome in zip(scores, outcomes)), Decimal(0)) / len(selections) if selections else None
    price_brier = sum(((price - outcome) ** 2 for price, outcome in zip(prices, outcomes)), Decimal(0)) / len(selections) if selections else None
    brier_skill = Decimal(1) - model_brier / price_brier if model_brier is not None and price_brier not in (None, 0) else None
    bands = []
    for label, low, high in BANDS:
        rows = [row for row in selections if low <= decimal(row["score"], "score") < high]
        observed = sum((Decimal(row["outcome_no"]) for row in rows), Decimal(0)) / len(rows) if rows else None
        scored = sum((decimal(row["score"], "score") for row in rows), Decimal(0)) / len(rows) if rows else None
        error = abs(observed - scored) if observed is not None else None
        bands.append({"band": label, "rows": len(rows), "independent_dates": len({row["market_date"] for row in rows}), "observed": None if observed is None else f"{observed:.8f}", "mean_score": None if scored is None else f"{scored:.8f}", "absolute_error": None if error is None else f"{error:.8f}", "represented": bool(rows), "passes": not rows or (len({row['market_date'] for row in rows}) >= 30 and error <= Decimal('0.05'))})
    returns = [decimal(row["submission_return"], "return") for row in selections]
    lower90, lower95 = clustered_lower(selections, "submission_return", Decimal("0.10")), clustered_lower(selections, "submission_return", Decimal("0.05"))
    holdouts = []
    for station in sorted(stations):
        rows = [row for row in selections if row["station_id"] != station]
        lower = clustered_lower(rows, "submission_return", Decimal("0.10"))
        holdouts.append({"excluded_station_id": station, "rows": len(rows), "lower_90_submission_return": None if lower is None else f"{lower:.8f}", "passes": lower is not None and lower >= 0})
    count_by_station = Counter(row["station_id"] for row in selections)
    station_share = Decimal(max(count_by_station.values(), default=0)) / len(selections) if selections else Decimal(1)
    date_share = Decimal(1) / len(selections) if selections else Decimal(1)
    proxies = [row for row in selections if row.get("public_trade_proxy") is not None]
    realized = sum(returns, Decimal(0))
    initial_gates = {
        "at_least_100_selected_dates": len(selections) >= 100 and len(dates) == len(selections),
        "at_least_8_selected_stations": len(stations) >= 8,
        "positive_brier_skill": brier_skill is not None and brier_skill > 0,
        "represented_reliability_bands": any(row["represented"] for row in bands) and all(row["passes"] for row in bands),
        "thirty_public_trade_proxies": len(proxies) >= 30 and len({row["market_date"] for row in proxies}) >= 30,
        "positive_exact_fee_proxy_pnl": realized > 0,
        "drawdown_at_most_five": maximum_drawdown(returns) <= Decimal("5"),
        "clustered_90_submission_return_positive": lower90 is not None and lower90 > 0,
        "leave_one_station_out": len(holdouts) >= 8 and all(row["passes"] for row in holdouts),
        "station_concentration": station_share <= Decimal("0.15"),
        "date_concentration": date_share <= Decimal("0.01"),
    }
    scale_gates = {"exact_250_selected_dates": len(selections) == 250 and len(dates) == 250, "clustered_95_submission_return_positive": lower95 is not None and lower95 > 0}
    scale_passes = all(initial_gates.values()) and all(scale_gates.values())
    projection = math.ceil(Decimal(100) / lower95) if scale_passes else None
    return {
        "selected_submissions": len(selections), "selected_dates": len(dates), "selected_stations": len(stations),
        "public_trade_proxies": len(proxies), "public_trade_proxy_dates": len({row["market_date"] for row in proxies}),
        "model_brier": None if model_brier is None else f"{model_brier:.8f}", "displayed_price_proxy_brier": None if price_brier is None else f"{price_brier:.8f}", "brier_skill": None if brier_skill is None else f"{brier_skill:.8f}",
        "reliability_bands": bands, "realized_public_trade_proxy_pnl": f"{realized:.4f}", "maximum_drawdown": f"{maximum_drawdown(returns):.4f}",
        "lower_90_submission_return": None if lower90 is None else f"{lower90:.8f}", "lower_95_submission_return": None if lower95 is None else f"{lower95:.8f}",
        "maximum_station_share": f"{station_share:.8f}", "maximum_date_share": f"{date_share:.8f}", "station_holdouts": holdouts,
        "initial_gates": initial_gates, "initial_economic_evidence_passes": all(initial_gates.values()), "failed_initial_gates": [key for key, value in initial_gates.items() if not value],
        "scale_gates": scale_gates, "scale_research_evidence_passes": scale_passes,
        "projected_contracts_to_100": projection, "projection_is_guaranteed": False,
        "provider_confirmed_fill_evidence": False, "capital_risk_authority": False, "production_activation": False,
        "selections": selections,
    }


def run_audit(report_path: Path, capture_path: Path, output_dir: Path, maximum: int, client_factory: Callable[[Path, int], PublicClient] = PublicClient) -> dict:
    parent, rows, models = verify_oos_artifact(report_path, capture_path)
    assert_not_production_host()
    if maximum != NETWORK_LIMIT:
        raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
    client = client_factory(output_dir, maximum)
    fees = [validate_fee_identity(client, series) for series in sorted(STATION_SERIES.values())]
    cutoffs = historical_cutoffs(client)
    quote_rows, by_date = [], defaultdict(list)
    funnel = {"source_station_dates": len(rows), "event_inventories": 0, "score_eligible_contracts": 0, "nonempty_candles": 0, "eligible_quotes": 0}
    for source in rows:
        series, market_date = STATION_SERIES[source["station_id"]], dt.date.fromisoformat(source["market_date"])
        markets = event_markets(client, series, market_date); funnel["event_inventories"] += 1
        for market in markets:
            candidate = score_contract(source, market, models)
            if candidate is None:
                continue
            funnel["score_eligible_contracts"] += 1
            quoted = capture_quote(client, series, candidate); quote_rows.append(quoted)
            if quoted["reason"] != "empty_candle": funnel["nonempty_candles"] += 1
            if quoted["candidate"] is True:
                funnel["eligible_quotes"] += 1; by_date[quoted["market_date"]].append(quoted)
    selections = []
    for market_date in date_range():
        candidates = by_date[market_date]
        if not candidates:
            continue
        candidates.sort(key=lambda row: (-decimal(row["conservative_edge"], "edge"), decimal(row["no_price_proxy"], "price"), -decimal(row["score"], "score"), row["market_ticker"]))
        selected = candidates[0]
        proxy = fetch_trade_proxy(client, selected, cutoffs["trades_created_ts"])
        selected["public_trade_proxy"] = proxy
        if proxy is None:
            selected["submission_return"] = "0"
        else:
            price, exact_fee = decimal(proxy["no_price"], "trade price"), decimal(proxy["fee"], "trade fee")
            selected["submission_return"] = str(Decimal(1) - price - exact_fee if selected["outcome_no"] == 1 else -price - exact_fee)
        selections.append(selected)
    evaluation = evaluate_selections(selections)
    output = {
        "schema": REPORT_SCHEMA, "parent_oos_run_id": OOS_RUN_ID, "parent_oos_head_sha": OOS_HEAD_SHA,
        "parent_oos_report_sha256": file_sha256(report_path), "parent_oos_capture_sha256": file_sha256(capture_path),
        "predeclaration_sha256": PREDECLARATION_SHA256, "research_only": True, "historical_price_data_inspected": True,
        "active_trading_capability_changed": False, "automatic_production_activation": False,
        "public_trade_proxy_is_provider_confirmed_fill": False, "historical_depth_known": False,
        "network_policy": {"maximum_requests": NETWORK_LIMIT, "actual_requests": client.used, "maximum_starts_per_second": 4, "no_retry": True, "stop_on_http_429": True},
        "fee_identities": fees, "historical_cutoffs": cutoffs, "support_funnel": funnel, "evaluation": evaluation, "quote_rows": quote_rows,
    }
    atomic_json(output_dir / "report.json", output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos-report", type=Path, required=True)
    parser.add_argument("--oos-capture", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-requests", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if file_sha256(root / "ECONOMICS_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Frozen economics predeclaration hash is invalid")
    if args.verify_only:
        report, rows, models = verify_oos_artifact(args.oos_report, args.oos_capture)
        print(json.dumps({"parent_oos_gate_passes": True, "report_sha256": file_sha256(args.oos_report), "capture_sha256": file_sha256(args.oos_capture), "rows": len(rows), "models": len(models), "decision": report["evaluation"]["diagnostic_decision"]}, sort_keys=True))
        return
    if args.output_dir is None or args.max_requests is None:
        raise ValueError("Network audit requires --output-dir and --max-requests")
    output = run_audit(args.oos_report, args.oos_capture, args.output_dir.resolve(), args.max_requests)
    print(json.dumps({"initial_economic_evidence_passes": output["evaluation"]["initial_economic_evidence_passes"], "scale_research_evidence_passes": output["evaluation"]["scale_research_evidence_passes"], "failed_initial_gates": output["evaluation"]["failed_initial_gates"], "network_requests": output["network_policy"]["actual_requests"]}, sort_keys=True))


if __name__ == "__main__":
    main()
