#!/usr/bin/env python3
"""Build and evaluate the frozen 615-date HRRRv4 station refit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import evaluate_hrrr_conservative_successor as calibration
import evaluate_hrrr_executable_economics as economics
import evaluate_hrrr_later_executable as predecessor

SCHEMA = "hrrr_v4_station_jeffreys_615_model_v1"
EVALUATION_SCHEMA = "hrrr_v4_station_jeffreys_615_untouched_evaluation_v1"
MODEL = "hrrr_v4_station_jeffreys_615_minus_0035_v1"
CORRECTION = Decimal("0.035")
SCORE_FLOOR = Decimal("0.900")
SCORE_QUANTUM = Decimal("0.000001")
TRAINING_DATES = 615
DEVELOPMENT_START, DEVELOPMENT_END = "2024-11-21", "2025-07-28"
UNTOUCHED_START, UNTOUCHED_END, UNTOUCHED_DATES = "2025-07-29", "2026-04-04", 250
FAILED_LATER_CAPTURE_SHA256 = "664ca7ab1ede95e8aaa5fb551d028945ada60d8149082061a56dd8a00e2c61ed"
FAILED_LATER_REPORT_SHA256 = "2d454cbd93d56e6cc4499dd463a97b47b0a2bd53eef93915c44d2aa841cf625f"
MODEL_ARTIFACT_SHA256 = "479f0a17b6ee4c773c7235cdd9316f1785970d2c3547034d311da45d6039058b"
PREDECLARATION_SHA256 = "b6a2c4ce9a91f730c5271baefbc10f96762500780abf538160790f4ee627b949"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def evaluate_with_model(
    capture_path: Path,
    models: dict[tuple[str, int], Decimal],
    baselines: dict[int, Decimal],
    start: str,
    end: str,
) -> dict:
    original = (predecessor.START, predecessor.END, predecessor.DATE_COUNT, predecessor.load_parent)
    predecessor.START = date.fromisoformat(start)
    predecessor.END = date.fromisoformat(end)
    predecessor.DATE_COUNT = UNTOUCHED_DATES
    predecessor.load_parent = lambda *_args: ({}, models, baselines)
    try:
        result = predecessor.evaluate_later_capture(Path("unused"), Path("unused"), capture_path)["evaluation"]
    finally:
        predecessor.START, predecessor.END, predecessor.DATE_COUNT, predecessor.load_parent = original
    gates = result["diagnostic_decision"]["gates"]
    gates["exact_250_untouched_dates"] = gates.pop("exact_250_later_dates")
    return result


def build_model(
    parent_report_path: Path,
    parent_capture_path: Path,
    development_capture_path: Path,
    failed_report_path: Path,
) -> dict:
    if sha256(development_capture_path) != FAILED_LATER_CAPTURE_SHA256 or sha256(failed_report_path) != FAILED_LATER_REPORT_SHA256:
        raise ValueError("Consumed later-window artifact identity changed")
    parent, _old_models, _old_baselines = predecessor.load_parent(parent_report_path, parent_capture_path)
    failed_expected = predecessor.evaluate_later_capture(parent_report_path, parent_capture_path, development_capture_path)
    if json.loads(failed_report_path.read_text(encoding="utf-8")) != failed_expected:
        raise ValueError("Failed predecessor report does not reproduce exactly")
    if failed_expected["evaluation"]["diagnostic_decision"]["passes"] is not False:
        raise ValueError("Successor requires the exact failed predecessor decision")

    parent_rows = calibration.load_capture(
        parent_capture_path,
        economics.START.isoformat(),
        economics.END.isoformat(),
        economics.DATE_COUNT,
    )
    counts = {
        (row["station_id"], row["distance_f"]): [row["successes"], row["samples"]]
        for row in parent["station_models"]
    }
    for row in parent_rows:
        for distance in economics.DISTANCES:
            counts[(row["station_id"], distance)][0] += int(Decimal(row["residual_f"]) <= distance)
            counts[(row["station_id"], distance)][1] += 1
    if set(counts) != {(station, distance) for station in economics.STATION_SERIES for distance in economics.DISTANCES}:
        raise ValueError("Refit station/distance inventory is incomplete")
    if any(samples != TRAINING_DATES for _successes, samples in counts.values()):
        raise ValueError("Refit model does not contain exactly 615 training dates")

    raw_models = {
        key: ((Decimal(successes) + Decimal("0.5")) / (samples + 1)).quantize(SCORE_QUANTUM)
        for key, (successes, samples) in counts.items()
    }
    models = {key: (value - CORRECTION).quantize(SCORE_QUANTUM) for key, value in raw_models.items()}
    baseline_counts = {
        distance: {
            "successes": sum(value[0] for key, value in counts.items() if key[1] == distance),
            "samples": sum(value[1] for key, value in counts.items() if key[1] == distance),
        }
        for distance in economics.DISTANCES
    }
    baselines = {
        distance: Decimal(value["successes"]) / value["samples"]
        for distance, value in baseline_counts.items()
    }
    development = evaluate_with_model(
        development_capture_path,
        models,
        baselines,
        DEVELOPMENT_START,
        DEVELOPMENT_END,
    )
    if development["diagnostic_decision"]["passes"] is not True:
        raise ValueError("Frozen refit does not pass its consumed development diagnostic")
    station_models = []
    for key in sorted(models):
        successes, samples = counts[key]
        station_models.append({
            "station_id": key[0],
            "distance_f": key[1],
            "samples": samples,
            "successes": successes,
            "raw_jeffreys_score": f"{raw_models[key]:.6f}",
            "corrected_score": f"{models[key]:.6f}",
        })
    return {
        "schema": SCHEMA,
        "model": MODEL,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "historical_price_data_inspected": False,
        "executable_economics_evaluated": False,
        "provider_confirmed_fill_evidence": False,
        "capital_risk_authority": False,
        "production_activation": False,
        "parent_oos_run_id": predecessor.PARENT_RUN_ID,
        "parent_oos_report_sha256": predecessor.PARENT_REPORT_SHA256,
        "parent_oos_capture_sha256": predecessor.PARENT_CAPTURE_SHA256,
        "failed_later_run_id": "33300096256",
        "failed_later_capture_sha256": FAILED_LATER_CAPTURE_SHA256,
        "failed_later_report_sha256": FAILED_LATER_REPORT_SHA256,
        "design": {
            "training_dates": TRAINING_DATES,
            "training_source": "original_365_plus_consumed_parent_oos_250",
            "correction": f"{CORRECTION:.6f}",
            "score_floor": f"{SCORE_FLOOR:.6f}",
            "distances_f": list(economics.DISTANCES),
            "development_start_market_date": DEVELOPMENT_START,
            "development_end_market_date": DEVELOPMENT_END,
            "development_receives_oos_credit": False,
            "untouched_start_market_date": UNTOUCHED_START,
            "untouched_end_market_date": UNTOUCHED_END,
            "untouched_independent_market_dates": UNTOUCHED_DATES,
        },
        "distance_training_climatology_counts": {
            str(key): value for key, value in baseline_counts.items()
        },
        "station_models": station_models,
        "development_evaluation": development,
    }


def model_maps(model: dict) -> tuple[dict[tuple[str, int], Decimal], dict[int, Decimal]]:
    if model.get("schema") != SCHEMA or model.get("model") != MODEL or model.get("research_only") is not True:
        raise ValueError("Frozen refit model identity is invalid")
    rows = model.get("station_models")
    if not isinstance(rows, list) or len(rows) != 80:
        raise ValueError("Frozen refit model inventory is incomplete")
    scores = {(row["station_id"], row["distance_f"]): Decimal(row["corrected_score"]) for row in rows}
    if set(scores) != {(station, distance) for station in economics.STATION_SERIES for distance in economics.DISTANCES}:
        raise ValueError("Frozen refit score grid is malformed")
    raw_baselines = model.get("distance_training_climatology_counts")
    if not isinstance(raw_baselines, dict) or set(raw_baselines) != {str(value) for value in economics.DISTANCES}:
        raise ValueError("Frozen refit climatology grid is malformed")
    baselines = {}
    for key, value in raw_baselines.items():
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("successes"), int)
            or not isinstance(value.get("samples"), int)
            or value["samples"] != TRAINING_DATES * len(economics.STATION_SERIES)
            or not 0 <= value["successes"] <= value["samples"]
        ):
            raise ValueError("Frozen refit climatology counts are malformed")
        baselines[int(key)] = Decimal(value["successes"]) / value["samples"]
    return scores, baselines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("build", "verify", "untouched"), required=True)
    parser.add_argument("--parent-report", type=Path, required=True)
    parser.add_argument("--parent-capture", type=Path, required=True)
    parser.add_argument("--development-capture", type=Path, required=True)
    parser.add_argument("--failed-report", type=Path, required=True)
    parser.add_argument("--model-artifact", type=Path)
    parser.add_argument("--untouched-capture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    expected = build_model(args.parent_report, args.parent_capture, args.development_capture, args.failed_report)
    if args.mode == "build":
        if args.output is None or args.model_artifact is not None or args.untouched_capture is not None:
            parser.error("build requires only --output")
        atomic_json(args.output, expected)
        print(json.dumps({"ok": True, "sha256": sha256(args.output)}))
        return
    if (
        args.model_artifact is None
        or sha256(args.model_artifact) != MODEL_ARTIFACT_SHA256
        or json.loads(args.model_artifact.read_text(encoding="utf-8")) != expected
    ):
        raise ValueError("Checked-in refit model does not reproduce exactly")
    if args.mode == "verify":
        if args.output is not None or args.untouched_capture is not None:
            parser.error("verify accepts no untouched capture or output")
        print(json.dumps({"ok": True, "model_sha256": sha256(args.model_artifact)}))
        return
    if args.untouched_capture is None or args.output is None:
        parser.error("untouched requires --untouched-capture and --output")
    scores, baselines = model_maps(expected)
    evaluation = evaluate_with_model(
        args.untouched_capture,
        scores,
        baselines,
        UNTOUCHED_START,
        UNTOUCHED_END,
    )
    report = {
        "schema": EVALUATION_SCHEMA,
        "model_artifact_sha256": sha256(args.model_artifact),
        "untouched_capture_sha256": sha256(args.untouched_capture),
        "research_only": True,
        "historical_price_data_inspected": False,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "executable_economics_evaluated": False,
        "provider_confirmed_fill_evidence": False,
        "capital_risk_authority": False,
        "production_activation": False,
        "design": expected["design"],
        "evaluation": evaluation,
    }
    atomic_json(args.output, report)
    print(json.dumps({"ok": True, "decision": evaluation["diagnostic_decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
