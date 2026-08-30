# Frozen HRRRv4 Low-Temperature Wilson Calibration

- Predeclared: 2026-08-30, before downloading or inspecting TMIN outcomes for either frozen window
- Purpose: weather-only calibration research; no price, depth, trade, fill, fee, capital, cohort, recommendation, or order authority
- Model: `hrrr_v4_low_temperature_station_wilson95_v1`
- Training dates: 2023-07-10 through 2024-03-15 inclusive, exactly 250 dates
- Untouched evaluation dates: 2024-03-16 through 2024-11-20 inclusive, exactly 250 dates

## Causal Hypothesis

Daily low-temperature markets are a materially different target from every consumed daily-high experiment. Public
Kalshi metadata on 2026-08-30 listed 20 active `KXLOWT*` daily series. Their aggregate series volume and the recent
68-date nested-event sample show executable market capacity before any low-temperature forecast outcome or causal quote
was inspected. The proposed trade family is NO on the lower extreme contract: a prior-day deterministic forecast places
the realized low sufficiently above the displayed cold-tail threshold, and the empirical station residual distribution
assigns at least 0.90 conservative probability that the lower-tail YES condition will fail.

The forecast feature is the minimum of the same exact eight native three-hour nearest-grid 2 m HRRRv4 values already
captured inside each station's local-standard climate day. The run initialized at prior-day 12Z and retains the fixed
20:00 UTC causal availability upper bound. Outcomes are NOAA NCEI Daily Summaries TMIN values bound through the exact
ICAO/WBAN/GHCN station identity already present in the parent artifacts. TMIN has not previously been downloaded or
inspected for either frozen interval.

## Frozen Model

For each of the exact 20 stations and distances 4, 5, 6, and 7°F, training success means:

`observed_min_f - forecast_min_f >= -distance_f`

The score is the one-sided 95% Wilson lower bound using fixed `z=1.6448536269514722`, rounded once to six decimal
places. There is no fitted haircut, station selection, pooling fallback, distance interpolation, or post-result
remapping. Only scores at least `0.900000` enter evaluation. Fixed reliability bands are `[0.900,0.925)` and
`[0.925,1.000)`.

## Untouched Decision

The 250-date untouched evaluation passes only if all of these are true:

- all 250 training dates and all 250 evaluation dates contain all exact 20 stations;
- at least 100 evaluation dates and at least eight stations have selected predictions;
- Brier skill is strictly positive against the distance-specific training climatology;
- both fixed reliability bands are represented on at least 30 independent dates and have absolute error at most 0.05;
- overall one-sided whole-date-clustered 90% and 95% observed-minus-score lower bounds are nonnegative;
- maximum station share is at most 0.35 and maximum date share is at most 0.05; and
- all 20 leave-one-station-out one-sided clustered-95 observed-minus-score bounds are nonnegative.

The deterministic whole-date bootstrap uses 10,000 samples and the existing fixed LCG seed. A failure consumes the
window and rejects this model without tuning. A pass is still only forecast calibration: it permits a separately frozen
Weather Company settlement-bridge and exact Kalshi quote/depth/trade/fee audit. NOAA TMIN is not silently treated as
the Kalshi settlement value, and no calibration pass can create trading authority.

## Source And Capability Boundary

The workflow restores only exact public research artifacts from runs `33204106231` and `33291428414`, verifies their
research-only identities, and makes exactly two credential-free NCEI Daily Summaries requests for TMIN. It has no
secret, production host, private Mimir database, Kalshi credential, order endpoint, deployment path, or trading
capability. Every output remains a checksum-bound public research artifact.
