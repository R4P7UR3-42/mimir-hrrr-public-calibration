# Later-window HRRRv4 executable-validation predeclaration

This document freezes one later-window validation of the already accepted
`hrrr_v4_station_jeffreys_minus_0035_v1` model before any Kalshi price or trade data from the new window is inspected.
The earlier exact-fee run remains valid but underpowered: its weather window from `2024-03-16` through `2024-11-20`
contained only 114 nonempty station/date market inventories on 28 independent dates, because broad daily-high market
publication began near the end of that period. It produced three score-eligible contracts, one nonempty candle, and no
eligible quote. That is a market-availability result, not adverse P&L and not permission to tune the policy.

## Immutable parent and later weather window

- Parent OOS run: `33291428414` at commit `d313b7bd86b2bc7e59de0411d2625d4191412895`.
- Parent report SHA-256: `a951a412e566a4bd4140b157249f28fafacf5482e8dac3092e1519c67b1be72f`.
- Parent capture SHA-256: `14605d9014131e9915c179c1a5b3f8f56de141430b0e418c8ab286e0eb7eac6b`.
- Model, station scores, correction, score floor, distance buckets, and reliability bands are inherited byte-for-byte
  from that passing parent. The later capture cannot retrain or alter them.
- The sole new window is exactly 250 dates from `2024-11-21` through `2025-07-28`, with all 20 frozen stations and the
  same HRRRv4 12Z/native-three-hour/20:00 UTC availability and NOAA daily-summary outcome identities.

The weather-only workflow must run first. It applies the frozen parent scores and training climatology to the new
capture and repeats the parent's complete gate family: at least 100 selected dates, at least eight stations, positive
Brier skill, all three fixed reliability bands represented by at least 30 dates with absolute error at most `0.05`,
nonnegative whole-date clustered one-sided 90% and 95% calibration margins, station share at most `0.35`, date share at
most `0.05`, and passing leave-one-station-out clustered-95 results for all 20 stations. Any failure stops before a
Kalshi client is constructed. A failure rejects this exact validation without score, date, station, or threshold tuning.

## Frozen executable economics

Only a successful exact-main later-weather workflow may trigger the price workflow. Economics retains every boundary
from `ECONOMICS_PREDECLARATION.md`:

- prior-date 20:05 UTC quote clock;
- exact daily-high station/series mapping, including Houston Hobby;
- binary greater-contract NO, distance `[4.0,8.0)`, frozen integer score bucket, and score at least `0.900`;
- implied NO price from the historical minute candle's `yes_bid.close` only;
- price `$0.70` through `$0.97`, depth unknown, exact quadratic fee
  `ceil_0.0001(0.07 * price * (1-price))`, and conservative edge at least `$0.015`;
- one selection per date by higher edge, lower price, higher score, then ticker;
- a non-block NO-taker trade of at least one contract during `[20:05,20:10)` no worse than the frozen limit is only a
  public trade-through proxy; absence receives zero return and no proxy is provider-confirmed fill evidence;
- returns use the decision limit and exact fee, never the observed trade price.

Initial evidence still requires at least 100 dates, eight stations, positive Brier skill versus implied price, every
represented fixed score band populated on at least 30 dates with absolute error at most `0.05`, at least 30 public
trade-through proxies on 30 dates, positive total exact-fee proxy P&L, drawdown at most `$5`, a strictly positive
whole-date-clustered one-sided 90% lower mean submission return, at least eight nonnegative leave-one-station-out
clustered-90 remainders, station share at most `0.15`, and date share at most `0.01`. Scale research evidence still
requires exactly 250 selected dates and a strictly positive clustered one-sided 95% lower mean. Only that lower bound
may support a non-guaranteed projection to `$100`.

## Acquisition and authority boundary

The later weather capture uses the existing checksum-bound public NOAA executable, at most 5,000 requests, concurrency
four, bounded decoder and outer timeouts, create-once artifacts, and pinned ecCodes. The economics run uses public Kalshi
GET endpoints only, at most 12,000 requests, no retry, at most four starts per second, and terminal HTTP 429 handling.
Both workflows use `/var/tmp`, upload checksummed immutable artifacts, and refuse the production Mimir host.

This validation is research only. It cannot provide provider-confirmed fills, capital authority, a production cohort,
recommendations, deployment authority, or orders. Any later trading decision requires a separate reviewed Mimir change
and preserves protected deployment, exact-runtime qualification, reconciliation, drawdown, concentration, and explicit
capital-risk gates.
