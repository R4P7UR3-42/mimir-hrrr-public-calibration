# Frozen HRRRv4 Refit Executable-Economics Audit

- Predeclared: 2026-08-30, after untouched weather acquisition run `33307452119` started and before its result or any price inspection
- Calibration run: `33307452119`
- Calibration head: `06208135423e919f7a7966166e4ae9f720c85a4b`
- Model: `hrrr_v4_station_jeffreys_615_minus_0035_v1`
- Window: 2025-07-29 through 2026-04-04, exactly 250 market dates
- Scope: public historical execution-proxy research only

The price audit is unreachable unless the exact triggering weather artifact reproduces byte-for-byte from the frozen
model and all twelve untouched calibration gates pass. A failed, skipped, later, branch, or different-head calibration
cannot construct the public-price client.

The audit changes no economic rule from the prior reviewed audit. At exactly 20:05 UTC on the day before each market
date, inspect only exact Kalshi daily-high greater-than contracts corresponding to the frozen station capture. Admit only
above-NO distance `[4.0°F,8.0°F)`, frozen score at least `0.900`, historical NO price proxy from `$0.70` through `$0.97`,
and exact quadratic taker-fee edge at least `$0.015`. Exact boundaries pass; immediately adjacent values fail. Select
at most one contract per date by higher conservative edge, lower price, higher score, then ticker.

Historical minute candles do not prove displayed depth or a Mimir fill. A qualifying non-block NO-taker trade within
five minutes at or below the limit is only a public trade-through proxy. A missing proxy receives zero return; it is not
treated as a fill or a loss. Exact-fee return is credited only to a proxy and uses the frozen one-contract price.

Initial research evidence requires at least 100 unique selected dates, at least eight stations, positive model Brier
skill versus displayed price, represented reliability bands with at least 30 dates and error at most `0.05`, at least
30 proxy dates, positive exact-fee proxy P&L, maximum drawdown at most `$5`, positive one-sided 90% whole-date clustered
return, nonnegative every-station holdouts, station share at most `0.15`, and date share at most `0.01`. Scale research
additionally requires exactly 250 selected dates and positive one-sided 95% whole-date clustered return.

The request ceiling is exactly 12,000, starts are limited to four per second, HTTP 429 is terminal, and no request is
retried. A passing audit remains research-only: the public proxy is not provider-confirmed fill evidence, historical
depth remains unknown, the `$100` projection is not guaranteed, and no adapter, policy, cohort, capital authority,
recommendation, production activation, or order authority is created.
