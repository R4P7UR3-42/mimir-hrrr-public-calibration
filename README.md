# Mimir HRRRv4 public calibration runner

This repository is an isolated, credential-free research runner. It contains no provider credentials, production
database, trading configuration, order capability, or production deployment path.

Archive-scale workflow state uses `/var/tmp` with `TMPDIR` set to the same root. `/tmp` is intentionally excluded
because it may be a capacity-limited RAM filesystem. Temporary workspace contents remain disposable and become
evidence only through the existing uploaded-artifact and checksum boundaries.

The two compressed executables are checksum-bound builds of the frozen private Mimir research source at
`55e6697381aafef7acf535ca64f0100dc426ca57`. The partial training artifact contains only public NOAA weather data and
324 complete dates from the predeclared 365-date training interval. Standard GitHub-hosted public runners resume the
remaining training dates and, only after separate review and dispatch, acquire the untouched 250-date evaluation
interval.

`assets/PUBLICATION_MANIFEST.json` binds the private source commit, original private workflow run and artifact digest,
both executable hashes, completed training-date range, and frozen untouched evaluation range.

Passing this workflow is research evidence only. It cannot authorize a strategy, recommendation, capital, deployment,
or order.

## Conservative station successor

The raw frozen HRRR station-Jeffreys model passed Brier skill and all reliability-band tolerances on its first 250-date
evaluation, but its worst leave-one-station-out clustered-95 calibration margin was `-0.026046`. That entire period is
now inspected development data.

The single successor `hrrr_v4_station_jeffreys_minus_0035_v1` subtracts exactly `0.035` from every station/distance
score: the predecessor deficit rounded up to the next `0.005`, plus one additional `0.005` buffer. It uses the existing
Stage-1-aligned score floor `0.900`, fixed bands `[0.900,0.925)`, `[0.925,0.950)`, and `[0.950,1.000)`, at least eight
selected stations, whole-date clustered bounds, concentration limits, positive Brier skill, and all 20 station
holdouts. No score, station, distance, or band is tuned separately.

Development replay retains 4,500 predictions across 11 stations and all 250 dates, positive Brier skill `0.117004`, a
clustered-95 lower calibration margin `+0.015468`, and worst station holdout `+0.011970`. This is model-development
support only. The sole independent OOS window is the immediately later 250 dates from `2024-03-16` through
`2024-11-20`. A failure rejects this successor without tuning. Even a pass permits only a separate executable-price,
exact-fee, depth, and fill audit; it creates no production or trading authority.

## Hard-gated executable economics

`ECONOMICS_PREDECLARATION.md` freezes a single public-price audit before price inspection. Its workflow restores only
untouched OOS run `33291428414`, validates every calibration gate offline, and does not construct the Kalshi client if
that identity fails. A passing parent may then be evaluated at the fixed 20:05 UTC quote clock with the frozen
`$0.70`–`$0.97` price interval, exact quadratic fees, `$0.015` edge floor, one selection per date, whole-date clustered
returns, station holdouts, concentration, and drawdown limits.

Completion of that one exact run triggers the economics workflow automatically only when both its run ID and head SHA
match. The downloaded report still has to pass the full offline semantic gate, so a green acquisition workflow with a
negative model decision cannot reach the price step.

Historical minute candles have no displayed-depth proof. The audit therefore labels a qualifying later public trade as
a trade-through proxy, assigns zero return when that proxy is absent, and never calls it a provider-confirmed fill.
Even positive initial or scale research evidence cannot authorize capital, deployment, recommendations, or orders.

The first economics run was structurally underpowered rather than economically negative: broad Kalshi daily-high
inventory existed on only 28 dates near the end of its 250-day weather window. `LATER_EXECUTABLE_PREDECLARATION.md`
therefore freezes one later 250-date validation from `2024-11-21` through `2025-07-28` without changing the already
passing model or any price, fee, edge, proxy, clustering, drawdown, or concentration boundary. A weather-only workflow
must pass every frozen calibration gate before a separate automatically triggered workflow can access later-window
prices. That handoff is bound to calibration run `33300096256` and exact acquisition head `58f8881a…`; a later run or
code revision cannot inherit price access. This successor remains research-only and non-authorizing.

## Dependency-free current transport cross-check

The one-time `Immutable current HRRR GRIB reference` workflow captures the exact 2026-08-29 12Z NOAA source at all nine
frozen steps and 20 stations using the already pinned ecCodes decoder and an exact 18-request budget. Its immutable
output exists only to compare NOAA's GRIB values with the NODD-listed MesoWest Zarr representation before considering a
native Deno transport. A mismatch rejects that transport. The canary cannot change calibration, economics, policy,
capital, cohort, production-provider, recommendation, or order authority.
