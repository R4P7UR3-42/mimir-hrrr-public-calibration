# GitHub Actions policy

This public research repository keeps exactly one persistent workflow: ordinary CI on pull requests and pushes to `main`. Standard GitHub-hosted runners for a public repository provide the reproducible verification boundary without consuming the private Mimir repository's Actions allowance.

Heavy acquisition, calibration, and economics jobs are reviewed one-shots:

1. Add a manually dispatched, exact-SHA, request-capped workflow in the same pull request as its frozen protocol.
2. Do not use schedules or `workflow_run` chains for research. Do not run both push and pull-request CI for the same feature-branch commit.
3. Cache exact public responses and long-running acquisition output in checksum-bound repository artifacts whenever their size is practical.
4. On terminal completion, commit the result and reusable cache, then delete the one-shot workflow. Never rerun a terminal audit to change its answer.
5. Keep continuous Mimir collection and trading on the production host under its reviewed service/scheduler boundary. GitHub Actions verifies code and initiates protected private deployment; it is not the trading runtime or a polling service.

Self-hosted GitHub runners are intentionally not used for public research. They add host security, cleanup, availability, and maintenance obligations without improving this solo repository's release boundary. A future one-shot workflow may be introduced only with a concrete frozen research question, explicit resource/request limits, and a deletion trigger.
