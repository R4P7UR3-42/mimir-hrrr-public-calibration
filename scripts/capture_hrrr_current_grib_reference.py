#!/usr/bin/env python3
"""Capture one immutable NOAA HRRR GRIB reference for Zarr transport validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA = "hrrr_v4_current_grib_station_reference_v1"
ORIGIN = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com"
RUN_DATE = "2026-08-29"
RUN_HOUR = 12
STEPS = (18, 21, 24, 27, 30, 33, 36, 39, 42)
MAX_REQUESTS = 18
STATIONS = (
    ("KATL", 33.640, -84.427), ("KAUS", 30.194, -97.670),
    ("KBOS", 42.365, -71.009), ("KDCA", 38.852, -77.037),
    ("KDEN", 39.856, -104.673), ("KDFW", 32.899, -97.040),
    ("KHOU", 29.646, -95.279), ("KLAS", 36.084, -115.153),
    ("KLAX", 33.942, -118.408), ("KMDW", 41.786, -87.752),
    ("KMIA", 25.795, -80.290), ("KMSP", 44.884, -93.222),
    ("KMSY", 29.993, -90.258), ("KNYC", 40.783, -73.967),
    ("KOKC", 35.393, -97.601), ("KPHL", 39.874, -75.242),
    ("KPHX", 33.435, -112.011), ("KSAT", 29.533, -98.469),
    ("KSEA", 47.450, -122.309), ("KSFO", 37.619, -122.375),
)


def urls(step: int) -> tuple[str, str]:
    if step not in STEPS:
        raise ValueError("Unsupported frozen HRRR forecast step")
    compact = RUN_DATE.replace("-", "")
    base = f"{ORIGIN}/hrrr.{compact}/conus/hrrr.t{RUN_HOUR:02d}z.wrfsfcf{step:02d}.grib2"
    return base, f"{base}.idx"


def parse_index(text: str, step: int) -> tuple[int, int, str]:
    compact = RUN_DATE.replace("-", "")
    rows: list[tuple[int, list[str], str]] = []
    for line in [value for value in text.splitlines() if value]:
        fields = line.split(":")
        if len(fields) < 6 or not fields[0].isdigit() or not fields[1].isdigit():
            raise ValueError("HRRR index contains a malformed row")
        rows.append((int(fields[1]), fields, line))
    matches = [
        index for index, (_offset, fields, _line) in enumerate(rows)
        if fields[2] == f"d={compact}{RUN_HOUR:02d}" and fields[3] == "TMP"
        and fields[4] == "2 m above ground" and fields[5] == f"{step} hour fcst"
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one exact HRRR temperature row; found {len(matches)}")
    index = matches[0]
    if index + 1 >= len(rows) or rows[index + 1][0] <= rows[index][0]:
        raise ValueError("HRRR index does not bound the exact temperature message")
    return rows[index][0], rows[index + 1][0] - 1, rows[index][2]


class BoundedClient:
    def __init__(self) -> None:
        self.requests = 0

    def get(self, url: str, byte_range: str | None = None) -> tuple[int, dict[str, str], bytes]:
        self.requests += 1
        if self.requests > MAX_REQUESTS:
            raise ValueError("HRRR reference exceeded its fixed request budget")
        headers = {"User-Agent": "mimir-hrrr-zarr-crosscheck/1"}
        if byte_range:
            headers["Range"] = byte_range
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read()
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise ValueError("HRRR reference stopped on HTTP 429") from error
            raise


def decode_message(path: Path, step: int) -> dict[str, object]:
    import eccodes

    with path.open("rb") as source:
        handle = eccodes.codes_grib_new_from_file(source)
        if handle is None:
            raise ValueError("HRRR reference contains no GRIB message")
        try:
            identity = {
                "short_name": eccodes.codes_get(handle, "shortName"),
                "level_type": eccodes.codes_get(handle, "typeOfLevel"),
                "level": int(eccodes.codes_get(handle, "level")),
                "grid_type": eccodes.codes_get(handle, "gridType"),
                "step_hours": int(eccodes.codes_get(handle, "step")),
                "data_date": str(eccodes.codes_get(handle, "dataDate")),
                "data_time": int(eccodes.codes_get(handle, "dataTime")),
                "packing_type": eccodes.codes_get(handle, "packingType"),
            }
            expected = ("2t", "heightAboveGround", 2, "lambert", step, RUN_DATE.replace("-", ""), 1200)
            actual = tuple(identity[key] for key in (
                "short_name", "level_type", "level", "grid_type", "step_hours", "data_date", "data_time"
            ))
            if actual != expected:
                raise ValueError(f"Unexpected HRRR GRIB identity: {actual!r}")
            extra = eccodes.codes_grib_new_from_file(source)
            if extra is not None:
                eccodes.codes_release(extra)
                raise ValueError("HRRR range contains more than one GRIB message")
            values = []
            for station_id, latitude, longitude in STATIONS:
                nearest = eccodes.codes_grib_find_nearest(handle, latitude, longitude, is_lsm=False, npoints=1)[0]
                kelvin = float(nearest["value"])
                distance_km = float(nearest["distance"])
                if not math.isfinite(kelvin) or not math.isfinite(distance_km) or distance_km > 5:
                    raise ValueError(f"Invalid nearest HRRR value for {station_id}")
                values.append({
                    "station_id": station_id,
                    "grid_latitude": str(nearest["lat"]),
                    "grid_longitude": str(nearest["lon"]),
                    "distance_km": format(distance_km, ".12f"),
                    "temperature_kelvin": format(kelvin, ".12f"),
                })
            identity["values"] = values
            identity["eccodes_version"] = eccodes.__version__
            return identity
        finally:
            eccodes.codes_release(handle)


def capture(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    client = BoundedClient()
    messages = []
    for step in STEPS:
        object_url, index_url = urls(step)
        status, _headers, index_bytes = client.get(index_url)
        if status != 200:
            raise ValueError(f"HRRR index returned {status}; expected 200")
        start, end, index_identity = parse_index(index_bytes.decode("utf-8"), step)
        status, headers, grib = client.get(object_url, f"bytes={start}-{end}")
        if status != 206:
            raise ValueError(f"HRRR range returned {status}; expected 206")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("content-range", ""))
        if not match or int(match.group(1)) != start or int(match.group(2)) != end:
            raise ValueError("HRRR Content-Range is missing or mismatched")
        if len(grib) != end - start + 1 or grib[:4] != b"GRIB" or grib[-4:] != b"7777":
            raise ValueError("HRRR range is truncated or malformed")
        path = output / f"step-{step:02d}.grib2"
        path.write_bytes(grib)
        decoded = decode_message(path, step)
        path.unlink()
        messages.append({
            "step_hours": step,
            "object_url": object_url,
            "index_url": index_url,
            "index_identity": index_identity,
            "range_start": start,
            "range_end": end,
            "object_length": int(match.group(3)),
            "message_sha256": hashlib.sha256(grib).hexdigest(),
            **decoded,
        })
    if client.requests != MAX_REQUESTS:
        raise ValueError("HRRR reference did not use its exact request budget")
    report = {
        "schema": SCHEMA,
        "research_only": True,
        "active_trading_capability_changed": False,
        "automatic_production_activation": False,
        "paid_provider_required": False,
        "run_date": RUN_DATE,
        "run_hour_utc": RUN_HOUR,
        "steps_hours": list(STEPS),
        "station_count": len(STATIONS),
        "request_count": client.requests,
        "messages": messages,
    }
    (output / "reference.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = capture(args.output_dir)
    print(json.dumps({"schema": report["schema"], "request_count": report["request_count"]}))


if __name__ == "__main__":
    main()
