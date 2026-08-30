#!/usr/bin/env python3
"""Hard-gated public executable-economics audit for the frozen HRRR refit."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Callable

import evaluate_hrrr_conservative_successor as calibration
import evaluate_hrrr_executable_economics as economics
import evaluate_hrrr_refit_successor as refit

CALIBRATION_RUN_ID = "33307452119"
CALIBRATION_HEAD_SHA = "06208135423e919f7a7966166e4ae9f720c85a4b"
RUN_SCHEMA = "hrrr_v4_station_jeffreys_615_untouched_run_v1"
ECONOMICS_SCHEMA = "hrrr_v4_station_jeffreys_615_executable_economics_v1"
PREDECLARATION_SHA256 = "96934ef2ff1fa5a6127bb482a2f7d35e411585dcadbe492c712bc0361660abcc"
NETWORK_LIMIT = 12_000
START = dt.date.fromisoformat(refit.UNTOUCHED_START)
END = dt.date.fromisoformat(refit.UNTOUCHED_END)


def expected_untouched_report(model: dict, model_path: Path, capture_path: Path) -> dict:
    scores, baselines = refit.model_maps(model)
    evaluation = refit.evaluate_with_model(
        capture_path,
        scores,
        baselines,
        refit.UNTOUCHED_START,
        refit.UNTOUCHED_END,
    )
    return {
        "schema": refit.EVALUATION_SCHEMA,
        "model_artifact_sha256": refit.sha256(model_path),
        "untouched_capture_sha256": refit.sha256(capture_path),
        "research_only": True,
        "historical_price_data_inspected": False,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "executable_economics_evaluated": False,
        "provider_confirmed_fill_evidence": False,
        "capital_risk_authority": False,
        "production_activation": False,
        "design": model["design"],
        "evaluation": evaluation,
    }


def verify_untouched(
    parent_report_path: Path,
    parent_capture_path: Path,
    development_capture_path: Path,
    failed_report_path: Path,
    model_path: Path,
    run_path: Path,
    untouched_capture_path: Path,
    untouched_report_path: Path,
) -> tuple[dict, list[dict], dict[tuple[str, int], Decimal]]:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if (
        run.get("schema") != RUN_SCHEMA
        or run.get("run_id") != CALIBRATION_RUN_ID
        or run.get("head_sha") != CALIBRATION_HEAD_SHA
        or run.get("research_only") is not True
        or run.get("active_trading_capability_changed") is not False
        or run.get("automatic_production_activation") is not False
    ):
        raise ValueError("Untouched calibration run identity is invalid")
    model = refit.build_model(
        parent_report_path,
        parent_capture_path,
        development_capture_path,
        failed_report_path,
    )
    if (
        refit.sha256(model_path) != refit.MODEL_ARTIFACT_SHA256
        or json.loads(model_path.read_text(encoding="utf-8")) != model
    ):
        raise ValueError("Frozen refit model does not reproduce exactly")
    expected = expected_untouched_report(model, model_path, untouched_capture_path)
    stored = json.loads(untouched_report_path.read_text(encoding="utf-8"))
    if stored != expected:
        raise ValueError("Untouched calibration report does not reproduce exactly")
    decision = stored.get("evaluation", {}).get("diagnostic_decision", {})
    if decision.get("passes") is not True or not all(decision.get("gates", {}).values()):
        raise ValueError("Untouched calibration did not pass every frozen gate")
    rows = calibration.load_capture(
        untouched_capture_path,
        refit.UNTOUCHED_START,
        refit.UNTOUCHED_END,
        refit.UNTOUCHED_DATES,
    )
    scores, _baselines = refit.model_maps(model)
    return stored, rows, scores


def run_economics(
    parent_report_path: Path,
    parent_capture_path: Path,
    development_capture_path: Path,
    failed_report_path: Path,
    model_path: Path,
    run_path: Path,
    untouched_capture_path: Path,
    untouched_report_path: Path,
    output_dir: Path,
    maximum: int,
    client_factory: Callable[[Path, int], economics.PublicClient] = economics.PublicClient,
) -> dict:
    untouched_report, rows, models = verify_untouched(
        parent_report_path,
        parent_capture_path,
        development_capture_path,
        failed_report_path,
        model_path,
        run_path,
        untouched_capture_path,
        untouched_report_path,
    )
    economics.assert_not_production_host()
    if maximum != NETWORK_LIMIT:
        raise ValueError(f"Frozen request ceiling is exactly {NETWORK_LIMIT}")
    client = client_factory(output_dir, maximum)
    fees = [
        economics.validate_fee_identity(client, series)
        for series in sorted(economics.STATION_SERIES.values())
    ]
    cutoffs = economics.historical_cutoffs(client)
    if economics.timestamp(cutoffs["market_settled_ts"], "market cutoff") < dt.datetime.combine(
        END + dt.timedelta(days=2), dt.time(), tzinfo=dt.timezone.utc
    ) or economics.timestamp(cutoffs["trades_created_ts"], "trade cutoff") <= economics.decision_clock(
        END
    ) + dt.timedelta(minutes=5):
        raise ValueError("Historical cutoff does not cover the frozen refit window")

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
    evaluation["projection_excludes_existing_realized_pnl"] = True
    evaluation["projection_is_capital_authority"] = False
    output = {
        "schema": ECONOMICS_SCHEMA,
        "calibration_run_id": CALIBRATION_RUN_ID,
        "calibration_head_sha": CALIBRATION_HEAD_SHA,
        "calibration_run_manifest_sha256": refit.sha256(run_path),
        "model_artifact_sha256": refit.sha256(model_path),
        "untouched_capture_sha256": refit.sha256(untouched_capture_path),
        "untouched_calibration_sha256": refit.sha256(untouched_report_path),
        "predeclaration_sha256": PREDECLARATION_SHA256,
        "research_only": True,
        "historical_price_data_inspected": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "public_trade_proxy_is_provider_confirmed_fill": False,
        "historical_depth_known": False,
        "capital_risk_authority": False,
        "production_activation": False,
        "network_policy": {
            "maximum_requests": NETWORK_LIMIT,
            "actual_requests": client.used,
            "maximum_starts_per_second": 4,
            "no_retry": True,
            "stop_on_http_429": True,
        },
        "untouched_calibration_decision": untouched_report["evaluation"]["diagnostic_decision"],
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
    parser.add_argument("--mode", choices=("verify", "economics"), required=True)
    parser.add_argument("--parent-report", type=Path, required=True)
    parser.add_argument("--parent-capture", type=Path, required=True)
    parser.add_argument("--development-capture", type=Path, required=True)
    parser.add_argument("--failed-report", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path, required=True)
    parser.add_argument("--calibration-run", type=Path, required=True)
    parser.add_argument("--untouched-capture", type=Path, required=True)
    parser.add_argument("--untouched-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-requests", type=int, default=NETWORK_LIMIT)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if refit.sha256(root / "REFIT_EXECUTABLE_ECONOMICS_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Frozen refit economics predeclaration hash is invalid")
    inputs = (
        args.parent_report,
        args.parent_capture,
        args.development_capture,
        args.failed_report,
        args.model_artifact,
        args.calibration_run,
        args.untouched_capture,
        args.untouched_report,
    )
    if args.mode == "verify":
        if args.output_dir is not None:
            parser.error("verify does not accept --output-dir")
        report, rows, models = verify_untouched(*inputs)
        print(json.dumps({
            "ok": True,
            "network_client_constructed": False,
            "rows": len(rows),
            "models": len(models),
            "decision": report["evaluation"]["diagnostic_decision"],
        }, sort_keys=True))
        return
    if args.output_dir is None:
        parser.error("economics requires --output-dir")
    report = run_economics(*inputs, args.output_dir, args.max_requests)
    print(json.dumps({
        "ok": True,
        "support_funnel": report["support_funnel"],
        "evaluation": report["evaluation"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
