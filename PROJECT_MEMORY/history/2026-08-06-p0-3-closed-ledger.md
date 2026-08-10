# P0-3 Fix — Closed Tombstone Ledger

Date: 2026-08-06

## Summary
Completed decisions are no longer deleted on capacity eviction. They are moved to a permanent
`closed` tombstone ledger so replay protection and identity-conflict semantics survive eviction.

## Changes
- `python/rill_xray_agent/state.py`: `closed` entries hold
  `{decisionIdHash, identityHash, payloadHash, closedAtEpochSeconds}`. `feedback` evicts the oldest
  `completed` entries into `closed` instead of dropping them. `register` and `feedback` consult
  `closed` for idempotency (same identity/payload) and conflict (different identity/payload).
- `python/rill_xray_agent/runtime_service.py`: the service transaction path mirrors the ledger
  semantics for register/feedback; eviction preserves the evicted entry's own identity.
- `tests/test_closed_ledger.py` (new): 6 tests covering eviction into `closed`, replay idempotency
  after eviction, replay conflict after eviction, register identity idempotency/conflict after
  eviction, and the low-level `RuntimeState` API.

## Verification
- 26 unit tests pass (6 new ledger tests).
- `scripts/run_all_checks.py`: source/process gates pass; manifest regenerated (117 entries).

## Status
- P0-3 complete. Remaining: P0-4 (root transaction state machine + recommendationId validation),
  IPC peer-credential authorization, bounded SQL concurrency and schema allowlist, cross-repo
  payload sync gate, Xray-side P0-5/6/7, then re-qualification.