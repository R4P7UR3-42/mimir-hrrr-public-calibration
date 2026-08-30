# HRRRv4 Low-Temperature Wilson-90 Successor Result

- Consumed: 2026-08-30
- Exact source commit: `ca7beba3d4fc3fff360adabd2aae11784d1a9cb8`
- Exact workflow run: `33319343801`
- Model: `hrrr_v4_low_temperature_station_wilson90_v1`
- Evaluation dates: 2024-11-21 through 2025-07-28
- Frozen diagnostic decision: pass

The one-shot evaluation consumed exactly one credential-free NOAA NCEI TMIN response. All 250 candidate market dates
had complete outcomes for all 20 station identities; no missing-source exclusion was used. The checksum-bound report
passed every predeclared calibration gate:

- 15,250 selected predictions across 16 stations and 250 independent market dates;
- mean score 0.972812 and observed success rate 0.980525;
- observed-minus-score margin +0.007712;
- Brier skill +0.098125 against the frozen distance-specific training climatology;
- whole-date-clustered lower margins +0.005024 at 90% and +0.004237 at 95%;
- fixed `[0.900,0.925)` band error 0.008658 and `[0.925,1.000)` band error 0.007628; and
- all concentration and 20 leave-one-station-out gates passed.

The GitHub workflow is red because its post-evaluation checksum command ran from the repository root while the checksum
manifest contains artifact-relative paths. The evaluator and artifact upload completed; the
subsequent terminal-preservation step correctly propagated that mechanical checksum-step outcome. The downloaded artifact's
manifest validates when checked from its artifact directory. This control defect does not change the frozen result and
is not a reason to query the consumed TMIN window again.

The complete raw source, model, report, and manifest are retained under
`data/results/hrrr-v4-low-temperature-wilson90-v1/`. Their key hashes are:

- evaluation report: `1e43d4806dca12721a99fa1787c278a729d055f4464e7aeb3196c53bc8bd2bb4`
- evaluation TMIN: `dccb0fd65c41fd610eac7c4f9ee7c20cbe78f9beafa0e07b1540dfc5759ada7a`
- model: `3d052664250c2a0acbfb52d38ff94cfad57eafbcd619acae5d56d5515fd376f1`

This is independent NOAA TMIN forecast-calibration evidence, not a profitability or trading claim. It contains no
Weather Company settlement bridge, Kalshi quote/depth/fee/fill evidence, capital decision, production policy, cohort,
recommendation, or order authority. It permits only the separately frozen next evaluation described in the original
predeclaration.
