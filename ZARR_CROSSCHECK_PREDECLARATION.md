# HRRR GRIB-to-Zarr transport cross-check

This one-time credential-free research canary captures the exact NOAA HRRRv4 12Z run dated 2026-08-29 at forecast
steps 18, 21, 24, 27, 30, 33, 36, 39, and 42 hours for the same frozen 20 stations used by the conservative station
model. It makes exactly one index and one byte-range request per step, stops on HTTP 429, validates complete GRIB and
ecCodes identities, and preserves message hashes plus nearest-grid values.

The output may be compared with the MesoWest-managed NODD-listed `hrrrzarr` representation only to determine whether a
dependency-free Deno transport can reproduce the frozen GRIB feature. It is not calibration, economics, fill, P&L,
capital, recommendation, cohort, order, production-provider, or activation evidence. A mismatch rejects the Zarr
transport; it cannot change the model, station grid, score, policy, or inspected OOS result.
