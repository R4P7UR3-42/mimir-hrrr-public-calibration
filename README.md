# Mimir HRRRv4 public calibration runner

This repository is an isolated, credential-free research runner. It contains no provider credentials, production
database, trading configuration, order capability, or production deployment path.

The two compressed executables are checksum-bound builds of the frozen private Mimir research source at
`55e6697381aafef7acf535ca64f0100dc426ca57`. The partial training artifact contains only public NOAA weather data and
324 complete dates from the predeclared 365-date training interval. Standard GitHub-hosted public runners resume the
remaining training dates and, only after separate review and dispatch, acquire the untouched 250-date evaluation
interval.

`assets/PUBLICATION_MANIFEST.json` binds the private source commit, original private workflow run and artifact digest,
both executable hashes, completed training-date range, and frozen untouched evaluation range.

Passing this workflow is research evidence only. It cannot authorize a strategy, recommendation, capital, deployment,
or order.
