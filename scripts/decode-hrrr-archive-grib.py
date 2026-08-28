#!/usr/bin/env python3
"""Decode one exact HRRRv4 2-m temperature GRIB message at frozen stations."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import eccodes


SCHEMA = "hrrr_v4_archive_station_decode_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grib", required=True)
    parser.add_argument("--stations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--step", required=True, type=int)
    parser.add_argument("--run-date", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stations = json.loads(Path(args.stations).read_text(encoding="utf-8"))
    if not isinstance(stations, list) or not stations:
        raise ValueError("Station input must be a nonempty list.")

    with Path(args.grib).open("rb") as source:
        handle = eccodes.codes_grib_new_from_file(source)
        if handle is None:
            raise ValueError("HRRR GRIB input contains no message.")
        try:
            short_name = eccodes.codes_get(handle, "shortName")
            level_type = eccodes.codes_get(handle, "typeOfLevel")
            level = int(eccodes.codes_get(handle, "level"))
            grid_type = eccodes.codes_get(handle, "gridType")
            step = int(eccodes.codes_get(handle, "step"))
            data_date = str(eccodes.codes_get(handle, "dataDate"))
            data_time = int(eccodes.codes_get(handle, "dataTime"))
            packing_type = eccodes.codes_get(handle, "packingType")
            if (
                short_name != "2t"
                or level_type != "heightAboveGround"
                or level != 2
                or grid_type != "lambert"
                or step != args.step
                or data_date != args.run_date.replace("-", "")
                or data_time != 1200
            ):
                raise ValueError(
                    "Unexpected HRRR GRIB identity: "
                    f"{short_name}/{level_type}/{level}/{grid_type}/{step}/{data_date}/{data_time}."
                )
            extra_handle = eccodes.codes_grib_new_from_file(source)
            if extra_handle is not None:
                eccodes.codes_release(extra_handle)
                raise ValueError("HRRR GRIB range contains more than one message.")

            values: list[dict[str, object]] = []
            for station in stations:
                station_id = station.get("station_id")
                latitude = station.get("latitude")
                longitude = station.get("longitude")
                if (
                    not isinstance(station_id, str)
                    or not station_id
                    or not isinstance(latitude, (int, float))
                    or not isinstance(longitude, (int, float))
                ):
                    raise ValueError("Station identity is malformed.")
                nearest = eccodes.codes_grib_find_nearest(
                    handle, float(latitude), float(longitude), is_lsm=False, npoints=1
                )[0]
                kelvin = float(nearest["value"])
                distance_km = float(nearest["distance"])
                if not math.isfinite(kelvin) or not math.isfinite(distance_km) or distance_km > 5:
                    raise ValueError(f"Invalid HRRR grid value for {station_id}.")
                values.append(
                    {
                        "station_id": station_id,
                        "grid_latitude": nearest["lat"],
                        "grid_longitude": nearest["lon"],
                        "distance_km": distance_km,
                        "temperature_kelvin": kelvin,
                    }
                )
        finally:
            eccodes.codes_release(handle)

    Path(args.output).write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "eccodes_version": eccodes.__version__,
                "step_hours": args.step,
                "short_name": short_name,
                "level_type": level_type,
                "level": level,
                "grid_type": grid_type,
                "packing_type": packing_type,
                "values": values,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
