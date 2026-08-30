# Frozen HRRRv4 Low-Temperature Wilson-90 Successor

- Predeclared: 2026-08-30, before downloading or inspecting any TMIN outcome in the successor window
- Model: `hrrr_v4_low_temperature_station_wilson90_v1`
- Training dates: 2023-07-10 through 2024-03-15, exactly 250 complete dates
- Untouched evaluation dates: 2024-11-21 through 2025-07-28, exactly 250 candidate dates
- Purpose: weather-only calibration research; no trading capability or authority

## Causal hypothesis and frozen adjustment

The causal lower-extreme NO hypothesis, forecast feature, exact station identities, distances 4/5/6/7°F, score floor
0.900000, reliability bands, and all concentration and clustered tests remain as originally declared. The sole model
adjustment is the one-sided Wilson lower-bound level from 95% to 90%, fixed at `z=1.2815515655446004`. This adjustment
was selected after the initial window and has no independent credit until this successor window is evaluated once.

The model artifact is frozen from the fully observed original 250-date training source. The successor workflow makes
exactly one credential-free NCEI request, for the untouched evaluation TMIN window.

## Frozen missing-source policy

NCEI omitted two TMIN fields in the first 250-date evaluation request. To prevent a single provider omission from
destroying an otherwise independent evaluation while preserving date clustering, any candidate date with a missing,
duplicate, malformed, or out-of-identity TMIN row for any required station is excluded in full from all 20 stations.
Partial dates are never evaluated. The report records every excluded date and station/reason identity.

At least 245 of the 250 candidate dates must be complete. Fewer than 245 complete dates is a terminal failure. The
missingness rule is source-availability handling only: it does not inspect outcomes when choosing exclusions and may
not change the model, gates, or thresholds.

## Untouched decision

The successor passes only if all of these are true:

- the checksum-bound frozen model contains all exact 20 stations, four distances, and 250 training samples per row;
- at least 245 complete evaluation dates remain after whole-date source exclusions;
- at least 100 selected dates and at least eight stations are represented;
- Brier skill is strictly positive against the frozen distance-specific training climatology;
- both fixed reliability bands occur on at least 30 dates and have absolute error at most 0.05;
- whole-date-clustered one-sided 90% and 95% observed-minus-score lower bounds are nonnegative;
- maximum station share is at most 0.35 and maximum date share is at most 0.05; and
- all 20 leave-one-station-out clustered-95 observed-minus-score bounds are nonnegative.

A failure consumes and rejects this successor without tuning. A pass is forecast calibration only. It permits a new,
separately frozen Weather Company settlement bridge and executable quote/depth/trade/fee audit; it cannot recommend,
activate a cohort, allocate capital, deploy a model, or place an order.

## Isolation

The workflow uses only public research artifacts and a free public NOAA endpoint. It has no secret, production host,
private Mimir database, Kalshi credential, order endpoint, deployment path, or paid dependency. Outputs are public,
checksum-bound research artifacts.
