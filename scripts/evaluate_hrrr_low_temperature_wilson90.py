#!/usr/bin/env python3
"""Evaluate the frozen Wilson-90 daily-low successor exactly once."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

BASE_PATH = Path(__file__).with_name("evaluate_hrrr_low_temperature.py")
SPEC = importlib.util.spec_from_file_location("low_temperature_base", BASE_PATH)
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

MODEL_SCHEMA = "hrrr_v4_low_temperature_station_wilson90_model_v1"
EVALUATION_SCHEMA = "hrrr_v4_low_temperature_station_wilson90_evaluation_v1"
MODEL = "hrrr_v4_low_temperature_station_wilson90_v1"
MODEL_SHA256 = "3d052664250c2a0acbfb52d38ff94cfad57eafbcd619acae5d56d5515fd376f1"
PREDECLARATION_SHA256 = "f40753d6335fc1d9d3981558c0a580681afa2943bb1061119269ee074b510b75"
EVALUATION = ("2024-11-21", "2025-07-28", 250, "33300096256")
WILSON_Z = Decimal("1.2815515655446004")
MINIMUM_COMPLETE_DATES = 245


def model_path() -> Path:
    return BASE_PATH.parents[1] / "data/frozen-models/hrrr-v4-low-temperature-station-wilson90-v1.json"


def load_frozen_model(stations: list[str]) -> tuple[dict, dict[tuple[str, int], Decimal], dict[int, Decimal]]:
    path = model_path()
    if base.sha256(path) != MODEL_SHA256:
        raise ValueError("Frozen Wilson-90 model checksum is invalid")
    model = json.loads(path.read_text())
    rows = model.get("station_models")
    if (
        model.get("schema") != MODEL_SCHEMA
        or model.get("model") != MODEL
        or model.get("wilson_z") != str(WILSON_Z)
        or model.get("training_start_market_date") != base.TRAINING[0]
        or model.get("training_end_market_date") != base.TRAINING[1]
        or model.get("training_independent_dates") != base.TRAINING[2]
        or model.get("distances_f") != list(base.DISTANCES)
        or model.get("score_floor") != base.fixed(base.SCORE_FLOOR)
        or not isinstance(rows, list)
        or len(rows) != len(stations) * len(base.DISTANCES)
    ):
        raise ValueError("Frozen Wilson-90 model identity is malformed")
    model_map: dict[tuple[str, int], Decimal] = {}
    base.WILSON_Z = WILSON_Z
    for row in rows:
        key = (row.get("station_id"), row.get("distance_f"))
        score = Decimal(str(row.get("wilson90_lower_score")))
        if (
            key[0] not in stations
            or key[1] not in base.DISTANCES
            or key in model_map
            or row.get("samples") != 250
            or not isinstance(row.get("successes"), int)
            or score != base.wilson_lower(row["successes"], row["samples"])
        ):
            raise ValueError("Frozen Wilson-90 station model is malformed")
        model_map[key] = score
    if set(model_map) != {(station, distance) for station in stations for distance in base.DISTANCES}:
        raise ValueError("Frozen Wilson-90 station inventory is incomplete")
    climatology = model.get("distance_training_climatology")
    baselines = {distance: Decimal(str(climatology[str(distance)])) for distance in base.DISTANCES}
    return model, model_map, baselines


def parse_whole_dates(body: bytes, station_to_ghcn: dict[str, str]) -> tuple[dict, list[dict], list[str]]:
    expected_dates = set(base.iso_dates(EVALUATION[0], EVALUATION[1]))
    reverse = {ghcn: station for station, ghcn in station_to_ghcn.items()}
    payload = json.loads(body)
    if not isinstance(payload, list):
        raise ValueError("NCEI TMIN response is malformed")
    values: dict[tuple[str, str], Decimal] = {}
    issues: dict[str, list[dict]] = defaultdict(list)
    for row_index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError("NCEI TMIN response contains a non-object row")
        market_date = row.get("DATE")
        station = reverse.get(row.get("STATION"))
        if market_date not in expected_dates:
            raise ValueError("NCEI TMIN response contains a date outside the frozen window")
        if station is None:
            issues[market_date].append({"reason": "unknown_station_identity", "source_station": row.get("STATION")})
            continue
        key = (station, market_date)
        if key in values:
            issues[market_date].append({"reason": "duplicate_row", "station_id": station})
            continue
        if "TMIN" not in row:
            issues[market_date].append({"reason": "missing_tmin", "station_id": station})
            continue
        try:
            value = Decimal(str(row["TMIN"]))
        except Exception:
            issues[market_date].append({"reason": "malformed_tmin", "station_id": station})
            continue
        if not value.is_finite() or not Decimal("-100") <= value <= Decimal("150"):
            issues[market_date].append({"reason": "invalid_tmin", "station_id": station})
            continue
        values[key] = value
    for market_date in sorted(expected_dates):
        for station in sorted(station_to_ghcn):
            if (station, market_date) not in values and not any(
                issue.get("station_id") == station for issue in issues[market_date]
            ):
                issues[market_date].append({"reason": "missing_row", "station_id": station})
    excluded_dates = sorted(market_date for market_date, date_issues in issues.items() if date_issues)
    complete_dates = sorted(expected_dates - set(excluded_dates))
    outcomes = {
        key: value for key, value in values.items() if key[1] in complete_dates
    }
    exclusions = [
        {"market_date": market_date, "issues": sorted(issues[market_date], key=lambda row: json.dumps(row, sort_keys=True))}
        for market_date in excluded_dates
    ]
    return outcomes, exclusions, complete_dates


def write_checksums(output_dir: Path) -> None:
    names = sorted(path.name for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(f"{base.sha256(output_dir / name)}  {name}" for name in names) + "\n"
    )


def run(evaluation_root: Path, output_dir: Path) -> dict:
    if base.sha256(BASE_PATH.parents[1] / "LOW_TEMPERATURE_WILSON90_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Wilson-90 predeclaration checksum is invalid")
    output_dir.mkdir(parents=True, exist_ok=False)
    stations, identity = base.load_parent_identity(evaluation_root, EVALUATION)
    model, model_map, baselines = load_frozen_model(stations)
    forecasts = base.load_forecast_minima(evaluation_root, EVALUATION)
    body, url = base.fetch_outcomes(identity, EVALUATION)
    (output_dir / "evaluation-tmin.json").write_bytes(body)
    outcomes, exclusions, complete_dates = parse_whole_dates(body, identity)
    joined = base.join_residuals(
        [row for row in forecasts if row["market_date"] in set(complete_dates)], outcomes
    )
    base.EVALUATION = EVALUATION
    result = base.evaluate(joined, model_map, baselines)
    gates = result["diagnostic_decision"]["gates"]
    gates.pop("exact_250_evaluation_dates")
    gates["at_least_245_complete_evaluation_dates"] = len(complete_dates) >= MINIMUM_COMPLETE_DATES
    gates["only_whole_dates_evaluated"] = len(joined) == len(complete_dates) * len(stations)
    result["diagnostic_decision"]["passes"] = all(gates.values())
    result["candidate_evaluation_dates"] = EVALUATION[2]
    result["complete_evaluation_dates"] = len(complete_dates)
    result["excluded_evaluation_dates"] = exclusions
    report = {
        "schema": EVALUATION_SCHEMA,
        "research_only": True,
        "historical_price_data_inspected": False,
        "weather_company_settlement_bridge_evaluated": False,
        "executable_economics_evaluated": False,
        "provider_confirmed_fill_evidence": False,
        "capital_risk_authority": False,
        "production_activation": False,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "design": {
            "model": MODEL,
            "model_sha256": MODEL_SHA256,
            "predeclaration_sha256": PREDECLARATION_SHA256,
            "evaluation_parent_run_id": EVALUATION[3],
            "evaluation_start_market_date": EVALUATION[0],
            "evaluation_end_market_date": EVALUATION[1],
            "candidate_evaluation_dates": EVALUATION[2],
            "minimum_complete_evaluation_dates": MINIMUM_COMPLETE_DATES,
            "missing_source_policy": "exclude_entire_market_date_if_any_required_station_row_is_unavailable",
            "distances_f": list(base.DISTANCES),
            "score_floor": base.fixed(base.SCORE_FLOOR),
            "wilson_z": str(WILSON_Z),
        },
        "source_evidence": {
            "network_requests": 1,
            "no_retry": True,
            "stop_on_http_429": True,
            "credential_required": False,
            "paid_provider_required": False,
            "evaluation_tmin_url": url,
            "evaluation_tmin_sha256": hashlib.sha256(body).hexdigest(),
        },
        "model_artifact": model,
        "evaluation": result,
        "limitations": [
            "This is NOAA TMIN forecast calibration only, not Kalshi settlement, price, depth, fee, fill, or P&L evidence.",
            "A pass permits only a separately frozen Weather Company settlement bridge and executable-economics audit.",
            "No result creates deployment, policy, cohort, capital, recommendation, or order authority.",
        ],
    }
    (output_dir / "model.json").write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    (output_dir / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_checksums(output_dir)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-capture-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.evaluation_capture_root, args.output_dir)
    except Exception as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "diagnostic.json").write_text(
            json.dumps({"schema": "hrrr_v4_low_temperature_wilson90_failure_v1", "error": str(error)}, indent=2) + "\n"
        )
        write_checksums(args.output_dir)
        raise
    print(json.dumps({"ok": True, "decision": report["evaluation"]["diagnostic_decision"]}))


if __name__ == "__main__":
    main()
