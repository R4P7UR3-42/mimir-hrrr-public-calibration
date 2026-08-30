# Initial HRRRv4 Low-Temperature Result

- Consumed: 2026-08-30
- Frozen model: `hrrr_v4_low_temperature_station_wilson95_v1`
- Frozen evaluation dates: 2024-03-16 through 2024-11-20
- Decision: rejected

The first frozen run downloaded both predeclared NOAA NCEI TMIN windows and then failed its complete-source gate. Two
of the required 5,000 evaluation station/date rows had no TMIN value: KSEA on 2024-04-25 and KSFO on 2024-09-14.
The exact 250-date window therefore cannot pass and receives no out-of-sample credit.

A development-only whole-date exclusion diagnostic dropped both incomplete dates from every station. On the remaining
248 dates, the original Wilson-95 model had positive Brier skill and positive whole-date-clustered margins, but its
fixed `[0.900,0.925)` reliability band had absolute error 0.055843, above the frozen 0.05 limit. That is a second
terminal failure. The diagnostic is post-result development, not independent evidence.

After consuming that result, a single model adjustment to a one-sided Wilson-90 lower bound was tested on the same
development rows. It passed the statistical gates on the 248 complete dates, including fixed-band errors of 0.048387
and 0.014134. This observation motivates a separately named successor and receives zero out-of-sample credit.

Source hashes:

- training TMIN: `523b670e0d2f5cc8fe9519b5a1447c1f709d578f925e313a6a8a4c3903a5f03d`
- evaluation TMIN: `8e6bcf7497bc37610a4a00060c1e0b10aefe1fd2049417203eceab09559c7457`
- development report: `21acccae3ccd00f25ef508ee21fc787301ecec617926c2f873e44ada750b8eed`

This result contains no Kalshi settlement, quote, fee, fill, P&L, capital, policy, cohort, recommendation, or order
authority.
