# Xray-Side P0-5/6/7 and Re-qualification Evidence

Date: 2026-08-06

## Summary
Recorded the re-qualification evidence for the Xray-side RC.2 blocker
closure: 20-round shuffled gate runs, fresh-clone gate, and the Xray
host regression results.

## Re-qualification
- `scripts/run_all_checks.py` with `RILL_GATE_ORDER_SEED` 0..19 (4-way
  parallel): 20/20 PASS.
- Fresh clone of `https://github.com/hello-yunshu/rill-xray-agent.git`
  at `fix/rc1-audit-blockers` (2a85aa1): all source/process gates pass.
- `PACKAGE_SHA256SUMS`: 137 entries. `PROJECT_MEMORY` chain: 10 records.

## Xray host side (commit fc08e30, PR #54)
- `.github/test/test_rill_xray_agent.sh`: host integration checks passed.
- `verify_repo.py --post-integration`: passed.
- Local regression suites: update metadata 12/12, offline commands 39/39,
  version loading 6/6.
- GitHub Actions: the `Rill Xray Agent` integration check passed on both
  the PR-triggered run (31116831828) and the push-triggered run
  (31116837525) for fc08e30; `security-regression` (update-sh metadata)
  passed on fc08e30 — the same job failed on the pre-fix commit
  d6872ec. The full-install matrix jobs of `test-install.yml` were
  cancelled at job setup / after hours queued by the GitHub action
  download outage ("Service Unavailable"); `Install (tls)` completed
  successfully. No code failure remained after the P0-5 fix.

## Delivery
- No RC.2 tag or release produced. The audited repair state lives on
  `fix/rc1-audit-blockers` and Xray `feat/rill-xray-agent` (PR #54).