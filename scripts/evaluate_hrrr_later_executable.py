#!/usr/bin/env python3
"""Hard-gated later-window calibration and economics for the frozen HRRRv4 model."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Callable

import evaluate_hrrr_conservative_successor as calibration
import evaluate_hrrr_executable_economics as economics

PARENT_RUN_ID = "33291428414"
PARENT_HEAD_SHA = "d313b7bd86b2bc7e59de0411d2625d4191412895"
PARENT_REPORT_SHA256 = "a951a412e566a4bd4140b157249f28fafacf5482e8dac3092e1519c67b1be72f"
PARENT_CAPTURE_SHA256 = "14605d9014131e9915c179c1a5b3f8f56de141430b0e418c8ab286e0eb7eac6b"
MODEL = economics.MODEL
START, END, DATE_COUNT = dt.date(2024, 11, 21), dt.date(2025, 7, 28), 250
CALIBRATION_SCHEMA = "hrrr_v4_frozen_model_later_validation_v1"
ECONOMICS_SCHEMA = "hrrr_v4_frozen_model_later_executable_economics_v1"
PREDECLARATION_SHA256 = "bfc97c05652b1d458e3e59ba49a90d7e6a1028de1978e3fac0dd4d4be4622be1"
NETWORK_LIMIT = 12_000


def fixed(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.6f}"


def maximum_share(values: list[str]) -> Decimal:
    return Decimal(max(Counter(values).values())) / len(values) if values else Decimal(0)


def load_parent(report_path: Path, capture_path: Path) -> tuple[dict, dict[tuple[str, int], Decimal], dict[int, Decimal]]:
    if economics.file_sha256(report_path) != PARENT_REPORT_SHA256 or economics.file_sha256(capture_path) != PARENT_CAPTURE_SHA256:
        raise ValueError("Parent OOS artifact hash is not the frozen passing identity")
    report, _rows, models = economics.verify_oos_artifact(report_path, capture_path)
    if report.get("design", {}).get("model") != MODEL:
        raise ValueError("Parent model identity drifted")
    station_models = report.get("station_models")
    if not isinstance(station_models, list):
        raise ValueError("Parent station models are missing")
    totals: dict[int, list[int]] = {distance: [0, 0] for distance in economics.DISTANCES}
    for row in station_models:
        distance = row.get("distance_f") if isinstance(row, dict) else None
        if distance not in totals or not isinstance(row.get("successes"), int) or not isinstance(row.get("samples"), int):
            raise ValueError("Parent training climatology is malformed")
        totals[distance][0] += row["successes"]
        totals[distance][1] += row["samples"]
    baselines = {distance: Decimal(successes) / samples for distance, (successes, samples) in totals.items() if samples > 0}
    if set(baselines) != set(economics.DISTANCES):
        raise ValueError("Parent training climatology is incomplete")
    return report, models, baselines


def evaluate_later_capture(
    parent_report_path: Path,
    parent_capture_path: Path,
    later_capture_path: Path,
) -> dict:
    _parent, models, baselines = load_parent(parent_report_path, parent_capture_path)
    rows = calibration.load_capture(later_capture_path, START.isoformat(), END.isoformat(), DATE_COUNT)
    predictions = []
    for row in rows:
        for distance in economics.DISTANCES:
            score = models[(row["station_id"], distance)]
            predictions.append({
                "station": row["station_id"],
                "date": row["market_date"],
                "distance": distance,
                "score": score,
                "baseline": baselines[distance],
                "outcome": Decimal(Decimal(row["residual_f"]) <= distance),
            })
    selected = [row for row in predictions if row["score"] >= economics.MIN_SCORE]
    margins = [(row["date"], row["outcome"] - row["score"]) for row in selected]
    brier = calibration.mean([(row["score"] - row["outcome"]) ** 2 for row in selected])
    baseline_brier = calibration.mean([(row["baseline"] - row["outcome"]) ** 2 for row in selected])
    brier_skill = None if baseline_brier in (None, 0) else Decimal(1) - brier / baseline_brier
    reliability = []
    for band_id, minimum, maximum in calibration.RELIABILITY_BANDS:
        band_rows = [row for row in selected if minimum <= row["score"] < maximum]
        margin = calibration.mean([row["outcome"] - row["score"] for row in band_rows])
        dates = len({row["date"] for row in band_rows})
        reliability.append({
            "band": band_id,
            "predictions": len(band_rows),
            "independent_market_dates": dates,
            "mean_score": fixed(calibration.mean([row["score"] for row in band_rows])),
            "observed_success_rate": fixed(calibration.mean([row["outcome"] for row in band_rows])),
            "observed_minus_score": fixed(margin),
            "ready": dates >= 30 and margin is not None and abs(margin) <= Decimal("0.05"),
        })
    holdouts = []
    for station in sorted(economics.STATION_SERIES):
        remainder = [row for row in selected if row["station"] != station]
        values = [(row["date"], row["outcome"] - row["score"]) for row in remainder]
        margin = calibration.mean([value for _, value in values])
        lower = calibration.clustered_lower(values, Decimal("0.05"))
        holdouts.append({
            "excluded_station": station,
            "predictions": len(remainder),
            "independent_market_dates": len({row["date"] for row in remainder}),
            "observed_minus_score": fixed(margin),
            "one_sided_95_date_clustered_lower_observed_minus_score": fixed(lower),
            "passes": margin is not None and lower is not None and margin >= 0 and lower >= 0,
        })
    selected_dates = len({row["date"] for row in selected})
    selected_stations = len({row["station"] for row in selected})
    lower90 = calibration.clustered_lower(margins, Decimal("0.10"))
    lower95 = calibration.clustered_lower(margins, Decimal("0.05"))
    gates = {
        "exact_250_later_dates": len({row["market_date"] for row in rows}) == DATE_COUNT,
        "at_least_100_selected_dates": selected_dates >= 100,
        "at_least_8_selected_stations": selected_stations >= 8,
        "positive_brier_skill": brier_skill is not None and brier_skill > 0,
        "exact_three_reliability_bands": len(reliability) == 3,
        "every_reliability_band_ready": all(row["ready"] for row in reliability),
        "date_clustered_90_margin_nonnegative": lower90 is not None and lower90 >= 0,
        "date_clustered_95_margin_nonnegative": lower95 is not None and lower95 >= 0,
        "station_concentration_at_most_0_35": maximum_share([row["station"] for row in selected]) <= Decimal("0.35"),
        "date_concentration_at_most_0_05": maximum_share([row["date"] for row in selected]) <= Decimal("0.05"),
        "exact_20_station_holdouts": len(holdouts) == 20,
        "every_station_holdout_passes": all(row["passes"] for row in holdouts),
    }
    return {
        "schema": CALIBRATION_SCHEMA,
        "parent_oos_run_id": PARENT_RUN_ID,
        "parent_oos_head_sha": PARENT_HEAD_SHA,
        "parent_oos_report_sha256": PARENT_REPORT_SHA256,
        "parent_oos_capture_sha256": PARENT_CAPTURE_SHA256,
        "later_capture_sha256": economics.file_sha256(later_capture_path),
        "predeclaration_sha256": PREDECLARATION_SHA256,
        "research_only": True,
        "historical_price_data_inspected": False,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "design": {
            "model": MODEL,
            "model_scores_inherited_from_parent": True,
            "evaluation_start_market_date": START.isoformat(),
            "evaluation_end_market_date": END.isoformat(),
            "independent_market_dates": DATE_COUNT,
            "score_floor": str(economics.MIN_SCORE),
            "distances_f": list(economics.DISTANCES),
            "reliability_bands": [band[0] for band in calibration.RELIABILITY_BANDS],
        },
        "evaluation": {
            "total_predictions": len(predictions),
            "selected_predictions": len(selected),
            "selected_stations": selected_stations,
            "selected_independent_market_dates": selected_dates,
            "mean_score": fixed(calibration.mean([row["score"] for row in selected])),
            "observed_success_rate": fixed(calibration.mean([row["outcome"] for row in selected])),
            "observed_minus_score": fixed(calibration.mean([value for _, value in margins])),
            "brier_score": fixed(brier),
            "distance_training_climatology_brier_score": fixed(baseline_brier),
            "brier_skill_versus_distance_training_climatology": fixed(brier_skill),
            "one_sided_90_date_clustered_lower_observed_minus_score": fixed(lower90),
            "one_sided_95_date_clustered_lower_observed_minus_score": fixed(lower95),
            "maximum_station_share": fixed(maximum_share([row["station"] for row in selected])),
            "maximum_date_share": fixed(maximum_share([row["date"] for row in selected])),
            "reliability": reliability,
            "leave_one_station_out": holdouts,
            "diagnostic_decision": {"passes": all(gates.values()), "gates": gates},
        },
    }


def verify_calibration(
    parent_report_path: Path,
    parent_capture_path: Path,
    later_capture_path: Path,
    calibration_report_path: Path,
) -> tuple[dict, list[dict], dict[tuple[str, int], Decimal]]:
    expected = evaluate_later_capture(parent_report_path, parent_capture_path, later_capture_path)
    stored = json.loads(calibration_report_path.read_text(encoding="utf-8"))
    if stored != expected:
        raise ValueError("Later calibration report does not exactly reproduce")
    decision = stored.get("evaluation", {}).get("diagnostic_decision", {})
    if decision.get("passes") is not True or not all(decision.get("gates", {}).values()):
        raise ValueError("Later calibration did not pass every frozen gate")
    _parent, models, _baselines = load_parent(parent_report_path, parent_capture_path)
    rows = calibration.load_capture(later_capture_path, START.isoformat(), END.isoformat(), DATE_COUNT)
    return stored, rows, models


def run_economics(
    parent_report_path: Path,
    parent_capture_path: Path,
    later_capture_path: Path,
    calibration_report_path: Path,
    output_dir: Path,
    maximum: int,
    client_factory: Callable[[Path, int], economics.PublicClient] = economics.PublicClient,
) -> dict:
    later_report, rows, models = verify_calibration(
        parent_report_path, parent_capture_path, later_capture_path, calibration_report_path
    )
    economics.assert_not_production_host()
    if maximum != NETWORK_LIMIT:
        raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
    client = client_factory(output_dir, maximum)
    fees = [economics.validate_fee_identity(client, series) for series in sorted(economics.STATION_SERIES.values())]
    cutoffs = economics.historical_cutoffs(client)
    if economics.timestamp(cutoffs["market_settled_ts"], "market cutoff") < dt.datetime.combine(
        END + dt.timedelta(days=2), dt.time(), tzinfo=dt.timezone.utc
    ) or economics.timestamp(cutoffs["trades_created_ts"], "trade cutoff") <= economics.decision_clock(END) + dt.timedelta(minutes=5):
        raise ValueError("Historical cutoff does not cover the later frozen window")
    quote_rows, by_date = [], defaultdict(list)
    funnel = {
        "source_station_dates": len(rows),
        "event_inventory_requests": 0,
        "nonempty_event_inventories": 0,
        "inventoried_markets": 0,
        "score_eligible_contracts": 0,
        "nonempty_candles": 0,
        "eligible_quotes": 0,
    }
    for source in rows:
        series = economics.STATION_SERIES[source["station_id"]]
        market_date = dt.date.fromisoformat(source["market_date"])
        markets = economics.event_markets(client, series, market_date)
        funnel["event_inventory_requests"] += 1
        funnel["nonempty_event_inventories"] += int(bool(markets))
        funnel["inventoried_markets"] += len(markets)
        for market in markets:
            candidate = economics.score_contract(source, market, models)
            if candidate is None:
                continue
            funnel["score_eligible_contracts"] += 1
            quoted = economics.capture_quote(client, series, candidate)
            quote_rows.append(quoted)
            funnel["nonempty_candles"] += int(quoted["reason"] != "empty_candle")
            if quoted["candidate"] is True:
                funnel["eligible_quotes"] += 1
                by_date[quoted["market_date"]].append(quoted)
    selections = []
    for market_date in economics.date_range(START, END):
        candidates = by_date[market_date]
        if not candidates:
            continue
        candidates.sort(key=lambda row: (
            -economics.decimal(row["conservative_edge"], "edge"),
            economics.decimal(row["no_price_proxy"], "price"),
            -economics.decimal(row["score"], "score"),
            row["market_ticker"],
        ))
        selected = candidates[0]
        proxy = economics.fetch_trade_proxy(client, selected, cutoffs["trades_created_ts"])
        selected["public_trade_proxy"] = proxy
        selected["submission_return"] = str(economics.supported_submission_return(selected, proxy))
        selections.append(selected)
    evaluation = economics.evaluate_selections(selections)
    output = {
        "schema": ECONOMICS_SCHEMA,
        "parent_oos_run_id": PARENT_RUN_ID,
        "parent_oos_head_sha": PARENT_HEAD_SHA,
        "parent_oos_report_sha256": PARENT_REPORT_SHA256,
        "parent_oos_capture_sha256": PARENT_CAPTURE_SHA256,
        "later_capture_sha256": economics.file_sha256(later_capture_path),
        "later_calibration_sha256": economics.file_sha256(calibration_report_path),
        "predeclaration_sha256": PREDECLARATION_SHA256,
        "research_only": True,
        "historical_price_data_inspected": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "public_trade_proxy_is_provider_confirmed_fill": False,
        "historical_depth_known": False,
        "network_policy": {
            "maximum_requests": NETWORK_LIMIT,
            "actual_requests": client.used,
            "maximum_starts_per_second": 4,
            "no_retry": True,
            "stop_on_http_429": True,
        },
        "later_calibration_decision": later_report["evaluation"]["diagnostic_decision"],
        "fee_identities": fees,
        "historical_cutoffs": cutoffs,
        "support_funnel": funnel,
        "evaluation": evaluation,
        "quote_rows": quote_rows,
    }
    economics.atomic_json(output_dir / "report.json", output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("calibration", "verify", "economics"), required=True)
    parser.add_argument("--parent-report", type=Path, required=True)
    parser.add_argument("--parent-capture", type=Path, required=True)
    parser.add_argument("--later-capture", type=Path, required=True)
    parser.add_argument("--calibration-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-requests", type=int, default=NETWORK_LIMIT)
    args = parser.parse_args()
    if args.mode == "calibration":
        if args.output is None or args.calibration_report is not None or args.output_dir is not None:
            parser.error("calibration requires only --output")
        report = evaluate_later_capture(args.parent_report, args.parent_capture, args.later_capture)
        economics.atomic_json(args.output, report)
        print(json.dumps({"ok": True, "decision": report["evaluation"]["diagnostic_decision"]}, sort_keys=True))
        return
    if args.calibration_report is None or args.output is not None:
        parser.error("verify/economics require --calibration-report")
    if args.mode == "verify":
        if args.output_dir is not None:
            parser.error("verify does not accept --output-dir")
        verify_calibration(args.parent_report, args.parent_capture, args.later_capture, args.calibration_report)
        print(json.dumps({"ok": True, "network_client_constructed": False}, sort_keys=True))
        return
    if args.output_dir is None:
        parser.error("economics requires --output-dir")
    report = run_economics(
        args.parent_report,
        args.parent_capture,
        args.later_capture,
        args.calibration_report,
        args.output_dir,
        args.max_requests,
    )
    print(json.dumps({"ok": True, "support_funnel": report["support_funnel"], "evaluation": report["evaluation"]}, sort_keys=True))


if __name__ == "__main__":
    main()
