# Frozen Low-Temperature Settlement And Executable-Economics Audit

- Predeclared: 2026-08-30, before inspecting any historical low-temperature market in the frozen 2024-11-21 through
  2025-07-28 evaluation window
- Parent: independently passing `hrrr_v4_low_temperature_station_wilson90_v1`
- Scope: public historical execution-proxy research only
- Capability: no credential, production host, recommendation, capital, cohort, deployment, or order authority

## Frozen contract hypothesis

For each of the exact 20 station/date rows, inspect only the lower outer `less` contract in the matching `KXLOWT*`
event. If its integer `cap_strike` is C, YES corresponds to an integer low below C and NO corresponds to an integer low
at least C. The causal forecast distance is:

`forecast_min_f - C + 0.5°F`

Only distances in `[4.0°F,8.0°F)` enter, using the already frozen station Wilson-90 score for floor(distance). The score
must be at least 0.900. The intended side is NO. Provider settlement must agree exactly with the frozen NCEI TMIN
integer outcome for every scored contract; any mismatch fails the settlement bridge.

## Frozen executable proxy

The decision clock is prior-day 20:05 UTC, five minutes after the parent HRRR availability upper bound. At exactly that
minute, infer a NO limit from the historical one-minute YES-bid close as `1 - YES bid`. Missing candles or book sides
are absent support, never imputed. Admit exact-cent NO limits from `$0.70` through `$0.97` with exact quadratic taker fee
`ceil($0.07 * price * (1-price), $0.0001)` and conservative edge at least `$0.015`.

Choose at most one row per independent market date by higher conservative edge, lower limit, higher score, then ticker.
A public execution proxy exists only when an exact non-block historical NO-taker trade of at least one contract occurred
within `[20:05,20:10)` UTC at or below the selected limit. It is not a provider-confirmed Mimir fill. A selected row
without that proxy contributes exactly zero return, not a simulated fill. A proxied row receives exact-fee settlement
return at its selected limit.

## Frozen decision gates

Settlement bridging requires all of the following:

- current series metadata remains Climate and Weather, quadratic fee multiplier one, and names The Weather Company
  `https://weather.com/kalshi` as settlement source;
- every historical event has one supported source identity and one exact lower outer contract;
- at least 100 scored independent dates and eight stations are represented; and
- zero provider-result/NCEI-result mismatches occur among scored contracts.

Initial executable evidence requires at least 100 selected independent dates, eight stations, positive model Brier skill
against displayed prices, every represented frozen reliability band on at least 30 dates with error at most 0.05, at
least 30 public trade proxies on 30 dates, positive exact-fee proxy P&L, drawdown at most `$5`, a strictly positive
whole-date-clustered 90% return bound, nonnegative leave-one-station-out 90% return bounds, maximum station share 0.15,
and maximum date share 0.01. Scale research additionally requires exactly 250 selected dates and a strictly positive
clustered 95% return bound. A `$100` contract-count projection may be reported only from that positive 95% lower bound
and is never guaranteed.

A failed gate consumes and rejects this exact economic policy without tuning. A pass is still public proxy research:
historical depth is unknown, displayed quotes do not prove our fill, and no result may change private Mimir or trade.

## Free and conserved infrastructure

The one-shot public workflow uses standard GitHub-hosted public-repository runners, the credential-free Kalshi public
API, the already committed NOAA source, and exact public parent artifacts. It makes no paid API call. It stops on HTTP
429, performs no retry, caps requests at 15,000 and starts at most four per second. After consumption, raw responses and
the report are checksum-bound and the network workflow is retired rather than rerun.
