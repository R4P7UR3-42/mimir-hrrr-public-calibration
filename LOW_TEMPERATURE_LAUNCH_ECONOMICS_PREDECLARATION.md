# Frozen Low-Temperature Launch-Window Economics Audit

- Predeclared: 2026-08-30, before acquiring HRRR, NCEI TMIN, historical candles, or trades for the launch window
- Model: unchanged `hrrr_v4_low_temperature_station_wilson90_v1`
- Exact window: 2026-04-03 through 2026-07-23, 112 independent market dates
- Scope: public historical validation research only; no trading authority

## Independence and inherited policy

The exact model, 20 station/series map, lower-outer NO contract, `[4.0°F,8.0°F)` distance, 0.900 score floor,
`$0.70`–`$0.97` price, `$0.015` exact-fee edge, prior-day 20:05 UTC quote clock, one selection per date, five-minute
public trade proxy, zero return for absent proxy, and every settlement, reliability, drawdown, concentration, and
holdout rule remain unchanged from `LOW_TEMPERATURE_ECONOMICS_PREDECLARATION.md`.

The prior zero-support run acquired series, fee, event, market, and cutoff inventory for all history, but its frozen
2024–2025 filter matched no event and its code read no launch-window outcome or contract. The raw responses remain
checksum-bound and are reused by exact request URL. The new window is selected solely because all 20 series have daily
event availability beginning 2026-04-03 and because it ends before the already inspected July 24–August 6 support
study. Provider outcomes exist inside the sealed inventory, so this is transparently an analysis-predeclared blinded
reuse, not a pristine acquisition claim. Historical candles, trade proxies, causal HRRR values, and NCEI TMIN outcomes
for the window remain uninspected.

## Causal sources

Acquire the same prior-day 12Z HRRRv4 native-grid feature for all 112 dates and 20 stations, retaining the fixed 20:00
UTC availability bound. Fetch NCEI TMIN exactly once. If any station outcome is missing or malformed, exclude that
entire date; require at least 110 complete dates. No partial date may enter. The frozen model is not refit.

Cached provider inventory must match its original exact URL and response SHA-256. It does not count against the new
network ceiling. Only missing exact responses, causal candles, and selected-date trades may use the public API.

## Decision

The settlement bridge requires at least 100 scored dates, eight stations, supported exact event sources, and zero
provider/NCEI settlement mismatches. Initial executable evidence requires at least 100 selected independent dates and
all previously frozen initial economic gates. Because the window has only 112 dates, it cannot satisfy or claim the
250-date scale gate. A pass permits only a bounded private implementation decision and prospective provider-confirmed
fill cohort; it is not fill evidence, capital authority, deployment, or a profit guarantee.

The public workflow uses free hosted runners and public NOAA/Kalshi endpoints, stops on HTTP 429, performs no retry,
and caps new economics requests at 10,000 with at most four starts per second. After one run it must publish checksums
and retire. Any result is terminal for this exact identity.
