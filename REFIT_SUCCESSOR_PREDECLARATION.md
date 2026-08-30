# Frozen 615-Date HRRRv4 Station Refit

- Predeclared: 2026-08-30, before acquisition or inspection of the new evaluation window
- Purpose: weather-only calibration research; no price, depth, trade, fill, capital, cohort, recommendation, or order authority
- Model: `hrrr_v4_station_jeffreys_615_minus_0035_v1`
- Model artifact SHA-256: `479f0a17b6ee4c773c7235cdd9316f1785970d2c3547034d311da45d6039058b`
- Untouched market dates: 2025-07-29 through 2026-04-04 inclusive, exactly 250 dates

## Predecessor Result

Exact run `33300096256` acquired and evaluated 250 dates from 2024-11-21 through 2025-07-28. Its capture SHA-256 is
`664ca7ab1ede95e8aaa5fb551d028945ada60d8149082061a56dd8a00e2c61ed`; its byte-reproduced report SHA-256 is
`2d454cbd93d56e6cc4499dd463a97b47b0a2bd53eef93915c44d2aa841cf625f`. Eleven of twelve gates passed, but excluding
`KLAS` or `KPHX` made the one-sided 95% date-clustered observed-minus-score margin negative. The predecessor therefore
failed. Its dates are inspected development data and receive no OOS, economics, profitability, or authorization credit.

## Frozen Successor

The successor makes one principled change: refit each exact station/distance Jeffreys score using the original 365
training dates plus the already-consumed 250 parent-OOS dates, for exactly 615 dates per station. It retains the exact
`0.035` correction, `0.900` score floor, distance buckets 4/5/6/7, 20-station inventory, three reliability bands,
whole-date deterministic clustered sampler, Brier comparison, concentration limits, and all 20 leave-one-station-out
tests. The failed predecessor window is used only to verify development reachability. The checked-in model artifact is
the complete frozen score grid and development result.

The checked-in artifact freezes each probability at six decimal places before development and untouched evaluation,
and stores exact integer successes and samples for every distance climatology instead of a rounded probability. The new
250-date capture must preserve exact HRRRv4 12Z, schedule-derived 20:00 UTC availability, native three-hour
nearest-grid feature, NOAA NCEI outcome, source hash, station, date, and completeness identities. Evaluation must use
only the checked-in model artifact. It passes only if all existing calibration gates pass. Failure consumes the dates
and stops this successor without price access or threshold adjustment.

Only a passing exact artifact may trigger a separately pinned executable-economics workflow. That later workflow may
still create no production adapter, strategy branch, cohort, capital authority, recommendation, or order.
