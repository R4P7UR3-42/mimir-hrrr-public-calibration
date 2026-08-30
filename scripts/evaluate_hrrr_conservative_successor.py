#!/usr/bin/env python3
"""Evaluate one frozen conservative HRRRv4 station-residual successor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 28

SCHEMA = "hrrr_v4_conservative_station_jeffreys_evaluation_v1"
CAPTURE_SCHEMA = "hrrr_v4_archive_calibration_capture_v1"
MODEL = "hrrr_v4_station_jeffreys_minus_0035_v1"
TRAINING_START, TRAINING_END, TRAINING_DATES = "2022-07-10", "2023-07-09", 365
WINDOWS = {
    "development": ("2023-07-10", "2024-03-15", 250),
    "oos": ("2024-03-16", "2024-11-20", 250),
}
DISTANCES = (4, 5, 6, 7)
CORRECTION = Decimal("0.035")
SCORE_FLOOR = Decimal("0.900")
RELIABILITY_BANDS = (
    ("0.900_0.925", Decimal("0.900"), Decimal("0.925")),
    ("0.925_0.950", Decimal("0.925"), Decimal("0.950")),
    ("0.950_1.000", Decimal("0.950"), Decimal("1.000")),
)
BOOTSTRAP_SAMPLES = 10_000
LCG_SEED = 0x5A17C9E3


def iso_dates(start: str, end: str) -> list[str]:
    current, final = date.fromisoformat(start), date.fromisoformat(end)
    values = []
    while current <= final:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def load_capture(path: Path, start: str, end: str, expected_dates: int) -> list[dict]:
    payload = json.loads(path.read_text())
    if (
        payload.get("schema") != CAPTURE_SCHEMA
        or payload.get("research_only") is not True
        or payload.get("active_trading_capability_changed") is not False
        or payload.get("automatic_production_activation") is not False
        or not isinstance(payload.get("rows"), list)
    ):
        raise ValueError("HRRR capture identity is not research-only")
    rows, identities = payload["rows"], set()
    expected = set(iso_dates(start, end))
    stations = set()
    for row in rows:
        identity = (row.get("station_id"), row.get("market_date"))
        if identity in identities:
            raise ValueError("HRRR capture repeats station/date identity")
        identities.add(identity)
        stations.add(identity[0])
        if (
            identity[1] not in expected
            or row.get("forecast_model") != "hrrr_v4_archive_3km_native_3h_nearest_v1"
            or row.get("forecast_availability_basis") != "hrrr_12z_operational_2000z_upper_bound_v1"
            or row.get("observation_source") != "noaa_ncei_daily_summaries_tmax"
            or not isinstance(row.get("forecast_source_composite_sha256"), str)
            or len(row["forecast_source_composite_sha256"]) != 64
        ):
            raise ValueError("HRRR capture row is outside the frozen identity")
        Decimal(row["residual_f"])
    observed_dates = {row["market_date"] for row in rows}
    if observed_dates != expected or len(observed_dates) != expected_dates or len(stations) != 20:
        raise ValueError("HRRR capture date/station coverage is incomplete")
    if len(rows) != expected_dates * 20:
        raise ValueError("HRRR capture row count is incomplete")
    return sorted(rows, key=lambda row: (row["market_date"], row["station_id"]))


def mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / len(values) if values else None


def clustered_lower(rows: list[tuple[str, Decimal]], tail: Decimal, samples: int = BOOTSTRAP_SAMPLES) -> Decimal | None:
    if not rows:
        return None
    groups = defaultdict(list)
    for cluster, value in rows:
        groups[cluster].append(value)
    clusters = [(sum((float(value) for value in groups[key]), 0.0), len(groups[key])) for key in sorted(groups)]
    state, results = LCG_SEED, []
    for _ in range(samples):
        total, count = 0.0, 0
        for _ in clusters:
            state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
            selected_sum, selected_count = clusters[(state * len(clusters)) // 0x100000000]
            total += selected_sum
            count += selected_count
        results.append(total / count)
    results.sort()
    return Decimal(str(results[math.floor((samples - 1) * float(tail))]))


def maximum_share(values: list[str]) -> Decimal:
    return Decimal(max(Counter(values).values())) / len(values) if values else Decimal(0)


def fixed(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.6f}"


def evaluate(training_rows: list[dict], evaluation_rows: list[dict], mode: str) -> dict:
    stations = sorted({row["station_id"] for row in training_rows})
    models = []
    model_by_key = {}
    for station in stations:
        station_rows = [row for row in training_rows if row["station_id"] == station]
        for distance in DISTANCES:
            successes = sum(Decimal(row["residual_f"]) <= distance for row in station_rows)
            raw = (Decimal(successes) + Decimal("0.5")) / (len(station_rows) + 1)
            corrected = max(Decimal(0), raw - CORRECTION)
            model = {
                "station_id": station,
                "distance_f": distance,
                "samples": len(station_rows),
                "successes": successes,
                "raw_jeffreys_score": fixed(raw),
                "corrected_score": fixed(corrected),
            }
            models.append(model)
            model_by_key[(station, distance)] = corrected
    baselines = {}
    for distance in DISTANCES:
        successes = sum(Decimal(row["residual_f"]) <= distance for row in training_rows)
        baselines[distance] = Decimal(successes) / len(training_rows)
    predictions = []
    for row in evaluation_rows:
        for distance in DISTANCES:
            score = model_by_key[(row["station_id"], distance)]
            outcome = Decimal(Decimal(row["residual_f"]) <= distance)
            predictions.append(
                {
                    "station": row["station_id"],
                    "date": row["market_date"],
                    "distance": distance,
                    "score": score,
                    "baseline": baselines[distance],
                    "outcome": outcome,
                }
            )
    selected = [row for row in predictions if row["score"] >= SCORE_FLOOR]
    margins = [(row["date"], row["outcome"] - row["score"]) for row in selected]
    brier = mean([(row["score"] - row["outcome"]) ** 2 for row in selected])
    baseline_brier = mean([(row["baseline"] - row["outcome"]) ** 2 for row in selected])
    brier_skill = None if baseline_brier in (None, 0) else Decimal(1) - brier / baseline_brier
    reliability = []
    for band_id, minimum, maximum in RELIABILITY_BANDS:
        rows = [row for row in selected if minimum <= row["score"] < maximum]
        margin = mean([row["outcome"] - row["score"] for row in rows])
        reliability.append(
            {
                "band": band_id,
                "predictions": len(rows),
                "independent_market_dates": len({row["date"] for row in rows}),
                "mean_score": fixed(mean([row["score"] for row in rows])),
                "observed_success_rate": fixed(mean([row["outcome"] for row in rows])),
                "observed_minus_score": fixed(margin),
                "ready": len({row["date"] for row in rows}) >= 30 and margin is not None and abs(margin) <= Decimal("0.05"),
            }
        )
    holdouts = []
    for station in stations:
        rows = [row for row in selected if row["station"] != station]
        values = [(row["date"], row["outcome"] - row["score"]) for row in rows]
        margin, lower = mean([value for _, value in values]), clustered_lower(values, Decimal("0.05"))
        holdouts.append(
            {
                "excluded_station": station,
                "predictions": len(rows),
                "independent_market_dates": len({row["date"] for row in rows}),
                "observed_minus_score": fixed(margin),
                "one_sided_95_date_clustered_lower_observed_minus_score": fixed(lower),
                "passes": margin is not None and lower is not None and margin >= 0 and lower >= 0,
            }
        )
    selected_dates = len({row["date"] for row in selected})
    selected_stations = len({row["station"] for row in selected})
    lower90 = clustered_lower(margins, Decimal("0.10"))
    lower95 = clustered_lower(margins, Decimal("0.05"))
    gates = {
        "exact_365_training_dates": len({row["market_date"] for row in training_rows}) == TRAINING_DATES,
        "exact_250_evaluation_dates": len({row["market_date"] for row in evaluation_rows}) == WINDOWS[mode][2],
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
        "schema": SCHEMA,
        "generated_at": None,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "design": {
            "model": MODEL,
            "mode": mode,
            "training_start_market_date": TRAINING_START,
            "training_end_market_date": TRAINING_END,
            "evaluation_start_market_date": WINDOWS[mode][0],
            "evaluation_end_market_date": WINDOWS[mode][1],
            "correction": fixed(CORRECTION),
            "correction_rule": "ceil predecessor worst leave-one-station-out clustered-95 deficit to 0.005 then add 0.005 buffer",
            "score_floor": fixed(SCORE_FLOOR),
            "distances_f": list(DISTANCES),
            "reliability_bands": [band[0] for band in RELIABILITY_BANDS],
        },
        "station_models": models,
        "evaluation": {
            "total_predictions": len(predictions),
            "selected_predictions": len(selected),
            "selected_stations": selected_stations,
            "selected_independent_market_dates": selected_dates,
            "mean_score": fixed(mean([row["score"] for row in selected])),
            "observed_success_rate": fixed(mean([row["outcome"] for row in selected])),
            "observed_minus_score": fixed(mean([value for _, value in margins])),
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
        "limitations": [
            "Development mode is inspected model-development evidence and receives no OOS credit.",
            "OOS mode is forecast calibration only, not price, fee, depth, fill, P&L, capital, cohort, or order evidence.",
            "A passing OOS result permits only a separate exact executable-economics audit on consumed dates.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--mode", choices=tuple(WINDOWS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    training = load_capture(args.training, TRAINING_START, TRAINING_END, TRAINING_DATES)
    start, end, count = WINDOWS[args.mode]
    evaluation = load_capture(args.evaluation, start, end, count)
    report = evaluate(training, evaluation, args.mode)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.write_text(encoded)
    print(json.dumps({"ok": True, "sha256": hashlib.sha256(encoded.encode()).hexdigest(), "decision": report["evaluation"]["diagnostic_decision"]}))


if __name__ == "__main__":
    main()
