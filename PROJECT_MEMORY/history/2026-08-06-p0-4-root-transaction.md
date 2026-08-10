# P0-4 Fix — RootTransaction Crash Recovery and recommendationId Validation

Date: 2026-08-06

## Summary
RootTransaction now covers the full crash-recoverable state machine
(`prepared → applying → applied → verified → commit-intent → committed`, with
`rollback-intent → rolledBack` / `rollbackUnverified` on the failure path) and
never uses `recommendationId` as a path.

## Changes
- `python/rill_xray_agent/root_txn.py`:
  - Work directories are `digest(recommendationId)`, never the raw id.
  - `recommendationId` validated against `^[A-Za-z0-9_-]{1,128}$` (defense in depth).
  - State machine written to `state.json` at every phase; every intermediate or
    `rollbackUnverified` state is recovered on startup: managed file restored from
    the prepare-time backup (path recorded in `backup-metadata.json`), generation
    restored, and a `rolledBack` commit bundle materialized so the transaction is
    terminal, auditable, and the system always knows the effective configuration.
  - `commit-intent` written before the bundle; `RILL_FAIL_AFTER_COMMIT_BUNDLE`
    injection retained.
- `python/rill_xray_agent/health.py`: `scan_transactions` skips non-directory
  entries (e.g. the single-flight lock file) so a healthy committed tree reports ready.
- `tests/test_root_txn_recovery.py` (new): 7 tests — hash directory usage, committed
  machine, rollback machine, recovery from each intermediate/unverified state,
  recommendationId path-safety, and health gating.
- `tests/test_reliability.py`: updated for hash work dirs; added rollback-restore
  and invalid-id rejection tests.

## Verification
- 34 unit tests pass (8 new root-txn tests).
- `scripts/run_all_checks.py`: source/process gates pass; manifest regenerated (120).

## Status
- P0-4 complete. Remaining: IPC peer-credential authorization, bounded SQL concurrency and
  schema allowlist, cross-repo payload sync gate, Xray-side P0-5/6/7, then re-qualification.