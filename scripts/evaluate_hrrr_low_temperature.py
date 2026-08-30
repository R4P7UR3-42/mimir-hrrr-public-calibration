#!/usr/bin/env python3
"""Build and evaluate the frozen HRRRv4 daily-low Wilson model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 40

MODEL_SCHEMA = "hrrr_v4_low_temperature_station_wilson95_model_v1"
EVALUATION_SCHEMA = "hrrr_v4_low_temperature_station_wilson95_evaluation_v1"
CAPTURE_SCHEMA = "hrrr_v4_archive_calibration_capture_v1"
EXTRACTION_SCHEMA = "hrrr_v4_archive_date_extraction_v1"
MODEL = "hrrr_v4_low_temperature_station_wilson95_v1"
PREDECLARATION_SHA256 = "08376d80a367adb57aa778b85b213d1637804ff8a76426849dd97855f50bd76d"
TRAINING = ("2023-07-10", "2024-03-15", 250, "33204106231")
EVALUATION = ("2024-03-16", "2024-11-20", 250, "33291428414")
DISTANCES = (4, 5, 6, 7)
SCORE_FLOOR = Decimal("0.900000")
WILSON_Z = Decimal("1.6448536269514722")
QUANTUM = Decimal("0.000001")
RELIABILITY_BANDS = (
    ("0.900_0.925", Decimal("0.900"), Decimal("0.925")),
    ("0.925_1.000", Decimal("0.925"), Decimal("1.000001")),
)
BOOTSTRAP_SAMPLES = 10_000
LCG_SEED = 0x5A17C9E3
NCEI_BASE = "https://www.ncei.noaa.gov/access/services/data/v1"


def iso_dates(start: str, end: str) -> list[str]:
    current, final = date.fromisoformat(start), date.fromisoformat(end)
    values: list[str] = []
    while current <= final:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fixed(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.quantize(QUANTUM, rounding=ROUND_HALF_UP):.6f}"


def mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / len(values) if values else None


def maximum_share(values: list[str]) -> Decimal:
    return Decimal(max(Counter(values).values())) / len(values) if values else Decimal(1)


def wilson_lower(successes: int, samples: int) -> Decimal:
    if not isinstance(successes, int) or not isinstance(samples, int) or samples < 1 or not 0 <= successes <= samples:
        raise ValueError("Wilson inputs are malformed")
    count, success = Decimal(samples), Decimal(successes)
    proportion = success / count
    z2 = WILSON_Z * WILSON_Z
    denominator = Decimal(1) + z2 / count
    center = proportion + z2 / (Decimal(2) * count)
    variance = (proportion * (Decimal(1) - proportion) + z2 / (Decimal(4) * count)) / count
    lower = (center - WILSON_Z * variance.sqrt()) / denominator
    return max(Decimal(0), lower).quantize(QUANTUM, rounding=ROUND_HALF_UP)


def clustered_lower(
    rows: list[tuple[str, Decimal]], tail: Decimal, samples: int = BOOTSTRAP_SAMPLES
) -> Decimal | None:
    if not rows:
        return None
    groups: dict[str, list[Decimal]] = defaultdict(list)
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


def load_parent_identity(root: Path, expected: tuple[str, str, int, str]) -> tuple[list[str], dict[str, str]]:
    start, end, count, _run_id = expected
    payload = json.loads((root / "capture.json").read_text())
    if (
        payload.get("schema") != CAPTURE_SCHEMA
        or payload.get("research_only") is not True
        or payload.get("active_trading_capability_changed") is not False
        or payload.get("automatic_production_activation") is not False
        or payload.get("coverage", {}).get("independent_market_dates") != count
        or payload.get("coverage", {}).get("complete_station_dates") != count * 20
        or payload.get("coverage", {}).get("complete") is not True
        or payload.get("design", {}).get("start_market_date") != start
        or payload.get("design", {}).get("end_market_date") != end
        or payload.get("design", {}).get("forecast_model") != "hrrr_v4_archive_3km_native_3h_nearest_v1"
        or payload.get("design", {}).get("forecast_availability_basis") != "hrrr_12z_operational_2000z_upper_bound_v1"
    ):
        raise ValueError("Parent HRRR capture identity is outside the frozen window")
    identities = payload.get("station_identities")
    if not isinstance(identities, list) or len(identities) != 20:
        raise ValueError("Parent station identities are incomplete")
    station_to_ghcn: dict[str, str] = {}
    for row in identities:
        station, ghcn = row.get("stationId"), row.get("ghcnStationId")
        if not isinstance(station, str) or not isinstance(ghcn, str) or station in station_to_ghcn:
            raise ValueError("Parent station identity is malformed")
        station_to_ghcn[station] = ghcn
    if len(set(station_to_ghcn.values())) != 20:
        raise ValueError("Parent GHCN identities are not unique")
    return sorted(station_to_ghcn), station_to_ghcn


def load_forecast_minima(root: Path, expected: tuple[str, str, int, str]) -> list[dict]:
    start, end, count, _run_id = expected
    stations, _ = load_parent_identity(root, expected)
    rows: list[dict] = []
    for market_date in iso_dates(start, end):
        path = root / "hrrr-v4" / f"{market_date}.json"
        extraction = json.loads(path.read_text())
        forecasts = extraction.get("station_forecasts")
        if (
            extraction.get("schema") != EXTRACTION_SCHEMA
            or extraction.get("market_date") != market_date
            or extraction.get("forecast_available_at") != f"{(date.fromisoformat(market_date) - timedelta(days=1)).isoformat()}T20:00:00.000Z"
            or extraction.get("forecast_availability_basis") != "hrrr_12z_operational_2000z_upper_bound_v1"
            or not isinstance(forecasts, list)
            or len(forecasts) != 20
        ):
            raise ValueError("HRRR low-temperature extraction identity is malformed")
        observed_stations: set[str] = set()
        for forecast in forecasts:
            station = forecast.get("station_id")
            points = forecast.get("grid_points")
            if station not in stations or station in observed_stations or not isinstance(points, list) or len(points) != 8:
                raise ValueError("HRRR low-temperature station/grid coverage is malformed")
            observed_stations.add(station)
            steps, temperatures = set(), []
            for point in points:
                step = point.get("step_hours")
                if not isinstance(step, int) or step in steps:
                    raise ValueError("HRRR low-temperature grid step is duplicated")
                steps.add(step)
                temperature = Decimal(str(point.get("temperature_f")))
                if not temperature.is_finite() or not Decimal("-100") <= temperature <= Decimal("150"):
                    raise ValueError("HRRR low-temperature grid value is invalid")
                temperatures.append(temperature)
            rows.append(
                {
                    "station_id": station,
                    "market_date": market_date,
                    "forecast_min_f": min(temperatures),
                    "forecast_available_at": extraction["forecast_available_at"],
                }
            )
        if observed_stations != set(stations):
            raise ValueError("HRRR low-temperature station inventory drifted")
    if len(rows) != count * 20:
        raise ValueError("HRRR low-temperature forecast coverage is incomplete")
    return sorted(rows, key=lambda row: (row["market_date"], row["station_id"]))


def ncei_url(station_to_ghcn: dict[str, str], start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "dataset": "daily-summaries",
            "stations": ",".join(station_to_ghcn[station] for station in sorted(station_to_ghcn)),
            "startDate": start,
            "endDate": end,
            "format": "json",
            "units": "standard",
            "includeAttributes": "true",
            "dataTypes": "TMIN",
        }
    )
    return f"{NCEI_BASE}?{query}"


def fetch_outcomes(station_to_ghcn: dict[str, str], expected: tuple[str, str, int, str]) -> tuple[bytes, str]:
    start, end, _count, _run_id = expected
    url = ncei_url(station_to_ghcn, start, end)
    request = urllib.request.Request(url, headers={"User-Agent": "mimir-hrrr-low-temperature-research/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise ValueError(f"NCEI TMIN returned {response.status}; expected 200")
            body = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise ValueError("NCEI TMIN capture stopped on HTTP 429") from error
        raise
    return body, url


def parse_outcomes(
    body: bytes, station_to_ghcn: dict[str, str], expected: tuple[str, str, int, str]
) -> dict[tuple[str, str], Decimal]:
    start, end, count, _run_id = expected
    reverse = {ghcn: station for station, ghcn in station_to_ghcn.items()}
    expected_dates = set(iso_dates(start, end))
    payload = json.loads(body)
    if not isinstance(payload, list):
        raise ValueError("NCEI TMIN response is malformed")
    outcomes: dict[tuple[str, str], Decimal] = {}
    for row in payload:
        station, market_date = reverse.get(row.get("STATION")), row.get("DATE")
        if station is None or market_date not in expected_dates or "TMIN" not in row:
            raise ValueError("NCEI TMIN row is outside the frozen identity")
        key = (station, market_date)
        value = Decimal(str(row["TMIN"]))
        if key in outcomes or not value.is_finite() or not Decimal("-100") <= value <= Decimal("150"):
            raise ValueError("NCEI TMIN row is duplicate or invalid")
        outcomes[key] = value
    if len(outcomes) != count * len(station_to_ghcn) or set(outcomes) != {
        (station, market_date) for station in station_to_ghcn for market_date in expected_dates
    }:
        raise ValueError("NCEI TMIN outcome coverage is incomplete")
    return outcomes


def join_residuals(forecasts: list[dict], outcomes: dict[tuple[str, str], Decimal]) -> list[dict]:
    rows = []
    for forecast in forecasts:
        key = (forecast["station_id"], forecast["market_date"])
        if key not in outcomes:
            raise ValueError("Low-temperature outcome join is incomplete")
        rows.append({**forecast, "observed_min_f": outcomes[key], "residual_f": outcomes[key] - forecast["forecast_min_f"]})
    return rows


def build_model(rows: list[dict]) -> tuple[dict, dict[tuple[str, int], Decimal], dict[int, Decimal]]:
    stations = sorted({row["station_id"] for row in rows})
    models, model_map = [], {}
    for station in stations:
        station_rows = [row for row in rows if row["station_id"] == station]
        for distance in DISTANCES:
            successes = sum(row["residual_f"] >= -Decimal(distance) for row in station_rows)
            score = wilson_lower(successes, len(station_rows))
            models.append(
                {
                    "station_id": station,
                    "distance_f": distance,
                    "samples": len(station_rows),
                    "successes": successes,
                    "wilson95_lower_score": fixed(score),
                }
            )
            model_map[(station, distance)] = score
    baselines = {}
    for distance in DISTANCES:
        baselines[distance] = Decimal(sum(row["residual_f"] >= -Decimal(distance) for row in rows)) / len(rows)
    model = {
        "schema": MODEL_SCHEMA,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "model": MODEL,
        "training_start_market_date": TRAINING[0],
        "training_end_market_date": TRAINING[1],
        "training_independent_dates": TRAINING[2],
        "score_floor": fixed(SCORE_FLOOR),
        "wilson_z": str(WILSON_Z),
        "distances_f": list(DISTANCES),
        "station_models": models,
        "distance_training_climatology": {str(distance): fixed(value) for distance, value in baselines.items()},
    }
    return model, model_map, baselines


def evaluate(rows: list[dict], model_map: dict[tuple[str, int], Decimal], baselines: dict[int, Decimal]) -> dict:
    predictions = []
    for row in rows:
        for distance in DISTANCES:
            score = model_map[(row["station_id"], distance)]
            predictions.append(
                {
                    "station": row["station_id"],
                    "date": row["market_date"],
                    "distance": distance,
                    "score": score,
                    "baseline": baselines[distance],
                    "outcome": Decimal(row["residual_f"] >= -Decimal(distance)),
                }
            )
    selected = [row for row in predictions if row["score"] >= SCORE_FLOOR]
    margins = [(row["date"], row["outcome"] - row["score"]) for row in selected]
    brier = mean([(row["score"] - row["outcome"]) ** 2 for row in selected])
    baseline_brier = mean([(row["baseline"] - row["outcome"]) ** 2 for row in selected])
    brier_skill = None if baseline_brier in (None, 0) else Decimal(1) - brier / baseline_brier
    reliability = []
    for band, minimum, maximum in RELIABILITY_BANDS:
        band_rows = [row for row in selected if minimum <= row["score"] < maximum]
        error = None
        if band_rows:
            error = abs(mean([row["outcome"] for row in band_rows]) - mean([row["score"] for row in band_rows]))
        dates = len({row["date"] for row in band_rows})
        reliability.append(
            {
                "band": band,
                "predictions": len(band_rows),
                "independent_market_dates": dates,
                "mean_score": fixed(mean([row["score"] for row in band_rows])),
                "observed_success_rate": fixed(mean([row["outcome"] for row in band_rows])),
                "absolute_error": fixed(error),
                "passes": dates >= 30 and error is not None and error <= Decimal("0.05"),
            }
        )
    holdouts = []
    for station in sorted({row["station"] for row in predictions}):
        values = [(row["date"], row["outcome"] - row["score"]) for row in selected if row["station"] != station]
        lower = clustered_lower(values, Decimal("0.05"))
        holdouts.append(
            {
                "excluded_station_id": station,
                "predictions": len(values),
                "independent_market_dates": len({market_date for market_date, _ in values}),
                "one_sided_95_date_clustered_lower_observed_minus_score": fixed(lower),
                "passes": lower is not None and lower >= 0,
            }
        )
    selected_dates = len({row["date"] for row in selected})
    selected_stations = len({row["station"] for row in selected})
    lower90 = clustered_lower(margins, Decimal("0.10"))
    lower95 = clustered_lower(margins, Decimal("0.05"))
    gates = {
        "exact_250_training_dates": True,
        "exact_250_evaluation_dates": len({row["market_date"] for row in rows}) == EVALUATION[2],
        "at_least_100_selected_dates": selected_dates >= 100,
        "at_least_8_selected_stations": selected_stations >= 8,
        "positive_brier_skill": brier_skill is not None and brier_skill > 0,
        "exact_two_reliability_bands": len(reliability) == 2,
        "every_reliability_band_passes": all(row["passes"] for row in reliability),
        "date_clustered_90_margin_nonnegative": lower90 is not None and lower90 >= 0,
        "date_clustered_95_margin_nonnegative": lower95 is not None and lower95 >= 0,
        "station_concentration_at_most_0_35": maximum_share([row["station"] for row in selected]) <= Decimal("0.35"),
        "date_concentration_at_most_0_05": maximum_share([row["date"] for row in selected]) <= Decimal("0.05"),
        "exact_20_station_holdouts": len(holdouts) == 20,
        "every_station_holdout_passes": all(row["passes"] for row in holdouts),
    }
    return {
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
    }


def run(training_root: Path, evaluation_root: Path, output_dir: Path) -> dict:
    if sha256(Path(__file__).parents[1] / "LOW_TEMPERATURE_PREDECLARATION.md") != PREDECLARATION_SHA256:
        raise ValueError("Low-temperature predeclaration hash is invalid")
    training_stations, training_identity = load_parent_identity(training_root, TRAINING)
    evaluation_stations, evaluation_identity = load_parent_identity(evaluation_root, EVALUATION)
    if training_stations != evaluation_stations or training_identity != evaluation_identity:
        raise ValueError("Low-temperature parent station identities drifted")
    training_forecasts = load_forecast_minima(training_root, TRAINING)
    evaluation_forecasts = load_forecast_minima(evaluation_root, EVALUATION)
    training_body, training_url = fetch_outcomes(training_identity, TRAINING)
    evaluation_body, evaluation_url = fetch_outcomes(evaluation_identity, EVALUATION)
    training_outcomes = parse_outcomes(training_body, training_identity, TRAINING)
    evaluation_outcomes = parse_outcomes(evaluation_body, evaluation_identity, EVALUATION)
    model, model_map, baselines = build_model(join_residuals(training_forecasts, training_outcomes))
    result = evaluate(join_residuals(evaluation_forecasts, evaluation_outcomes), model_map, baselines)
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
            "predeclaration_sha256": PREDECLARATION_SHA256,
            "training_parent_run_id": TRAINING[3],
            "evaluation_parent_run_id": EVALUATION[3],
            "training_start_market_date": TRAINING[0],
            "training_end_market_date": TRAINING[1],
            "evaluation_start_market_date": EVALUATION[0],
            "evaluation_end_market_date": EVALUATION[1],
            "forecast_feature": "minimum exact eight native-three-hour HRRRv4 values in local-standard climate day",
            "outcome_source": "noaa_ncei_daily_summaries_tmin",
            "distances_f": list(DISTANCES),
            "score_floor": fixed(SCORE_FLOOR),
            "wilson_z": str(WILSON_Z),
            "reliability_bands": [band for band, _, _ in RELIABILITY_BANDS],
        },
        "source_evidence": {
            "network_requests": 2,
            "no_retry": True,
            "stop_on_http_429": True,
            "credential_required": False,
            "paid_provider_required": False,
            "training_tmin_url": training_url,
            "training_tmin_sha256": hashlib.sha256(training_body).hexdigest(),
            "evaluation_tmin_url": evaluation_url,
            "evaluation_tmin_sha256": hashlib.sha256(evaluation_body).hexdigest(),
        },
        "model_artifact": model,
        "evaluation": result,
        "limitations": [
            "This result is NOAA TMIN forecast calibration only and is not Kalshi settlement, price, depth, fee, fill, or P&L evidence.",
            "A pass permits only a separate frozen Weather Company settlement bridge and executable-economics audit.",
            "No result creates model deployment, policy, cohort, capital, recommendation, or order authority.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    encoded_model = json.dumps(model, indent=2, sort_keys=True) + "\n"
    encoded_report = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (output_dir / "model.json").write_text(encoded_model)
    (output_dir / "evaluation.json").write_text(encoded_report)
    (output_dir / "training-tmin.json").write_bytes(training_body)
    (output_dir / "evaluation-tmin.json").write_bytes(evaluation_body)
    checksums = []
    for name in ("model.json", "evaluation.json", "training-tmin.json", "evaluation-tmin.json"):
        checksums.append(f"{sha256(output_dir / name)}  {name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-capture-root", type=Path, required=True)
    parser.add_argument("--evaluation-capture-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.training_capture_root, args.evaluation_capture_root, args.output_dir)
    print(json.dumps({"ok": True, "decision": report["evaluation"]["diagnostic_decision"]}))


if __name__ == "__main__":
    main()
