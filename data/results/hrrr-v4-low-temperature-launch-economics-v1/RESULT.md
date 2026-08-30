# HRRR v4 low-temperature launch-window economics result

The frozen `hrrr_v4_low_temperature_wilson90_launch_executable_economics_v1` audit is terminal and rejected for implementation or promotion.

- Source run: `33324929234` at exact head `fbecb87f0360ae96b65e36a63bd7101d852721d4`
- Report SHA-256: `cb89830c8328205ad9a8b9150d4d584634623cf4978c5cd6ff8e4eeccc8f3e22`
- Complete weather dates: 111 of 112
- Settlement-bridge support: 88 dates across 16 stations; required at least 100 dates
- Executable selections: 10 dates across 4 stations
- Public trade proxies: 2; required at least 30
- Exact-fee public-proxy P&L: `+$0.2262`
- Maximum drawdown: `$0.0000`
- Clustered 90% lower submission return: `0.00000000`; required positive
- Brier skill versus displayed price proxy: `-0.19062161`; required positive
- Reliability absolute errors: `0.07769700` and `0.09765244`; both failed
- Initial economics gates: 2 passed, 9 failed

The small positive proxy P&L is sparse diagnostic evidence, not a profit claim. Fixing the separate settlement-source-label diagnostic cannot repair the independent support, executable-date, station-diversity, trade-proxy, calibration, clustered-return, holdout, and concentration failures. No production or trading capability changed.
