# HRRRv4 conservative successor executable-economics predeclaration

This document freezes the only executable-economics audit permitted for
`hrrr_v4_station_jeffreys_minus_0035_v1` before any historical Kalshi price or trade data is inspected.

## Parent evidence gate

The audit may start only from GitHub Actions run `33291428414` at exact source commit
`d313b7bd86b2bc7e59de0411d2625d4191412895`. The downloaded artifact must contain the exact research-only HRRR capture
for all 20 stations on all 250 dates from `2024-03-16` through `2024-11-20` and an OOS evaluation whose complete frozen
diagnostic decision passes. A missing, malformed, partial, development-mode, failed, or differently identified artifact
stops before a Kalshi client is created. There is no fallback run or threshold retuning.

## Causal contract and quote identity

- Forecast information is available at 20:00 UTC on the prior calendar date. The sole quote clock is 20:05 UTC.
- The inventory is the exact NWS daily-high Kalshi series mapped to the 20 HRRR stations. Houston is `KXHIGHTHOU` and
  therefore binds Hobby (`KHOU`), never Intercontinental.
- Only binary `greater` contracts are eligible. Buying NO succeeds exactly when the finalized high is at or below the
  integer floor strike. Provider result and frozen NOAA outcome must agree.
- Contract distance is `floor + 0.5 - forecast_high`. It must be in `[4.0, 8.0)`. Its conservative score is the frozen
  station model at `floor(distance)`; only the predeclared integer buckets 4, 5, 6, and 7 exist.
- The minute candle's current `yes_bid.close_dollars` field is used only as an implied NO taker-price proxy,
  `1 - YES bid`. The legacy `close` field is not admitted. Missing, boundary, non-cent, or ambiguous candles are not
  candidates. Historical candles do not prove displayed depth.
- Exact `$0.70` and `$0.97` pass; adjacent values outside the interval fail. Exact-fee conservative edge must be at
  least `$0.015`; equality passes. Fee is `ceil_0.0001(0.07 * price * (1-price))`, after exact series fee-history checks.
- At most one row is selected per market date by higher conservative edge, then lower implied NO price, higher frozen
  score, and ticker. No station, date, strike, score, band, price, or edge is tuned after inspection.

## Execution proxy and economic decisions

A public non-block NO-taker trade for at least one contract, priced no worse than the frozen limit during
`[20:05,20:10)`, is a conservative public trade-through proxy. Acquisition must request `is_block_trade=false`, and
every returned row must explicitly contain `is_block_trade=false`; a missing or true value fails closed. It is not a
claim that Mimir would have filled and is never counted as provider-confirmed execution evidence. A selected submission
without that proxy receives zero return. A supported selection receives exact-fee return `1-price-fee` on a NO win and
`-price-fee` on a loss.

Initial economic evidence requires every item below:

1. the parent OOS gate above;
2. at least 100 selected independent market dates and at least eight selected stations;
3. positive Brier skill against implied price and every represented fixed score band `[0.900,0.925)`, `[0.925,0.950)`,
   `[0.950,1.000)` containing at least 30 dates with absolute calibration error at most `0.05`;
4. at least 30 public trade-through proxies on 30 dates;
5. positive total exact-fee proxy P&L, maximum drawdown at most `$5`, and a strictly positive whole-date-clustered
   one-sided 90% lower mean submission return;
6. at least eight represented leave-one-station-out remainders, each with nonnegative clustered-90 lower return;
7. maximum station share at most `0.15` and maximum date share at most `0.01`.

Scale research evidence additionally requires 250 selected dates and a strictly positive whole-date-clustered
one-sided 95% lower mean submission return. A non-guaranteed projection to `$100` may be reported only from that lower
95% mean. This audit never supplies provider-confirmed fill evidence, capital authority, a production cohort, a
recommendation, deployment authority, or an order.

## Acquisition boundary

The audit uses only public Kalshi GET endpoints, at most 12,000 requests, at most four starts per second, no retry, and
terminal handling of HTTP 429. It records request URLs, response hashes, headers, and raw bodies in a create-once
artifact. It refuses to run on a production Mimir host.
