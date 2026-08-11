# 2026-08-11 — 0.2 Phase-1 P1 convergence fix (journal, feedback, delivery, PID1)

## Scope
Execution of the Phase-1 P1 convergence round on the frozen 0.2 tree
(`feat/0.2-operational-intelligence`, Rill) with canonical reseal and Xray
payload sync (`feat/rill-xray-agent-0.2`). No feature work; minimal fixes to
close the remaining P1 items.

## P1-1 + P1-2 — EventJournal (commit `daec959`)
- Torn-tail fail-closed: a torn (newline-incomplete) tail is legal only on
  the NEWEST active segment (writer truncates, reader skips). A partial tail
  on any closed historical segment is evidence corruption and now fails
  closed for writers AND readers (`EventJournalError` "torn tail in closed
  segment") instead of silent truncation/skip.
- Segment aggregation: appends reuse the active segment (`nextSegment - 1`)
  and rotate exactly once at the `segment_bytes` boundary; the journal is a
  bounded segmented ring again (was one segment per event).
- Crash-safety contract unchanged: event fsync, meta recovery, monotonic
  sequence, rollover victim deletion after commit, symlink rejection,
  single-writer lock, total byte bound.
- Regression: `tests/test_event_journal_segmenting.py` (cases A-D);
  `test_duplicate_sequence_fails_closed` updated for aggregation.

## P1-3 — Closed-ledger feedback identity (commit `9062414`)
- An evicted Doctor decision previously lost its feedback projection
  identity (capability/modelGeneration): the CLI only resubmits
  decisionId/outcome/helpful/diagnosisCorrect, so exact replays degraded to
  capability=None/modelGeneration=0 and misjudged the same feedback as a
  conflict.
- Eviction tombstones now persist the SAFE non-sensitive identity metadata
  (never raw config/secrets/free text); the evicted-replay path rebuilds the
  canonical projection from it. Exact replay stays idempotent after eviction
  and across Runtime restart; changed outcome/helpful/diagnosisCorrect still
  fails closed. Legacy tombstones keep the old fallback.
- Regression: `tests/test_closed_feedback_replay.py` (real max_completed=1
  eviction via the diagnose->feedback lifecycle).

## P1-4 — Targeted OI PID1 qualification (evidence `f8685ad`)
- The copied generic 66-check PID1 logs were replaced with targeted OI logs
  produced on fresh systemd-PID1 containers against the frozen 0.2 tree
  (bundle `00c0ee1b770e`, SHA-verified bootstrap install).
- Items per distro (24/24 PASS): systemd as PID1; bootstrap re-run
  idempotent; config invariants (observe-only, routeAssist/boundedAuto
  false); DAC observation contract (Runtime read OK, overwrite denied,
  history-tree create denied, 640/2750 ownership, socket 660); OI lifecycle
  observe->timeline->diagnose->feedback->inspect; diagnosis idempotency
  (same evidence -> same decisionId, also after restart); feedback accepted
  then exact-replay idempotent after restart (closed-ledger metadata
  identity path).
- Debian 12 (bookworm) and Ubuntu 24.04: both PASS
  (`qualification/debian12-oi02-pid1.log`,
  `qualification/ubuntu2404-oi02-pid1.log`).

## P1-5 — Bootstrap delivery regression (commit `862e778` + Xray `1ac35d9`)
- The mandatory delivery proof (`sudo bash .github/test/test_rill_bootstrap_
  delivery.sh`) was removed from the Xray host suite in `3281a83`; restored
  in the Xray suite and the Rill mirror.

## Reseal + sync
- Canonical bundle resealed: `00c0ee1b770e3bfd3316b5d1c3a7143b1dccf159755f
  a2dd26594c0b92dc13e3`; CANONICAL_MANIFEST.json rebuilt (69 files);
  PACKAGE_SHA256SUMS regenerated (217 entries).
- Rill canonical production commit: `862e7781ae708ed2397faa9ac2e086ecb828b197`
  (Xray workflow `RILL_CANONICAL_COMMIT` bump).
- Xray payload synced via `apply_to_repo.py`; local canonical verification
  PASS (38 files, bundle `00c0ee1b770e`).

## Gates
- Rill `run_all_checks.py`: exit 0 (26 isolated python modules; canonical
  payload sync PASS 69 files bundle `00c0ee1b770e`; package sums 217).
- Journal suite 40 PASS; feedback/closed-ledger suite 62 PASS.
