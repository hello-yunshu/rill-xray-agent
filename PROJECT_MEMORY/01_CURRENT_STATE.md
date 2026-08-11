# Current state

v0.1.0 is RELEASED (tag `v0.1.0`, stable GitHub Release published, artifacts +
SHA256SUMS published). Development has advanced to **0.2 Operational
Intelligence** on the `feat/0.2-operational-intelligence` branch (cut from
`v0.1.0`), version `0.2.0-alpha.1`. The v0.1.0 tag/release are frozen and are
not modified by 0.2 development.

## 0.2 Phase-1 implementation (merged-into-branch, CI-green)
- **Safe Event Timeline**: bounded, crash-safe journal of meaningful
  state-change events (`event_journal.py`, `events.py`,
  `schemas/xray-event.v1.schema.json`). Ring-buffer rollover, atomic fsync'd
  appends, symlink rejection, corrupt-entry detection, read-only mode.
- **Doctor v1**: deterministic advisory-only diagnosis (`doctor.py`,
  `schemas/doctor-result.v1.schema.json`). 12 rules; facts separated from
  inferences; coarse confidence; fixed templates; `canApply=false`.
- **Structured Feedback**: enum/boolean/scalar-only allowlist
  (`payload_policy.sanitize_doctor_feedback`); free-text/secrets/config
  rejected.
- **Runtime API**: `timeline` + `diagnose`; runtime reads observer history
  but never appends (ReadOnlyPaths).
- **CLI**: `timeline`, `diagnose`, `feedback`; semantic capability labels
  (sentinel/doctor/route).
- **Xray integration**: Diagnostic menu item + non-interactive
  `diagnose`/`timeline` in the canonical manager and install.sh offline-safe
  flags; canonical bundle resealed and synced to Xray.

## 0.2 audit fix (this round, committed `cdd0f50`)
- **CLI feedback dispatch fix**: `feedback` subparser was registered but
  missing from the CLI dispatch dict, so `--json feedback …` crashed with
  `KeyError` instead of submitting structured feedback. Added `feedback` to
  the dispatch table + regression test `tests/test_cli_dispatch.py` covering
  every subcommand's dispatch path via a fake runtime.
- **DAC observation permission contract** (root observer / unprivileged
  Runtime): observation tree is `root:rill-xray-agent` with `2750` setgid
  directories; the root observer writes `0640 root:rill-xray-agent`; the
  Runtime user reads but cannot write or create. Enforced in
  `rill_xray_agent_install.sh`, the observe systemd unit
  (`User=root Group=rill-xray-agent UMask=0027`) and the runtime unit
  (`ReadOnlyPaths=/var/lib/rill-xray-agent-xray`).

## 0.2 P1 convergence fix (this round, commits `daec959`/`9062414`/`862e778`)
- **EventJournal torn-tail fail-closed (P1-1)**: a torn (newline-incomplete)
  tail is legal only on the NEWEST active segment (crash torn write -> writer
  truncates, reader skips). A partial tail on any closed historical segment
  is evidence corruption and fails closed (`EventJournalError` "torn tail in
  closed segment") for writers AND readers instead of silent truncation.
- **Segment aggregation (P1-2)**: appends reuse the active segment and rotate
  exactly once at the `segment_bytes` boundary (`nextSegment` = newest+1),
  instead of creating one segment per event. The journal is a bounded
  segmented ring again; crash-safety contract unchanged. Regression suite
  `tests/test_event_journal_segmenting.py` (cases A-D), plus
  `test_duplicate_sequence_fails_closed` updated for aggregation.
- **Closed-ledger feedback identity (P1-3)**: a completed Doctor decision
  evicted to the ClosedLedger lost its feedback projection identity
  (capability/modelGeneration), degrading exact feedback replays to a
  different payload hash (false conflict). Eviction tombstones now persist the
  SAFE non-sensitive identity metadata; the evicted-replay path rebuilds the
  canonical projection from it. Exact replay stays idempotent after eviction
  and across Runtime restart; changed outcome/helpful/diagnosisCorrect still
  fails closed; legacy tombstones keep the old fallback. Regression suite
  `tests/test_closed_feedback_replay.py`.
- **Bootstrap delivery regression restored**: the mandatory delivery proof
  (`sudo bash .github/test/test_rill_bootstrap_delivery.sh`) was removed from
  the Xray host suite in `3281a83`; restored in both the Xray suite and the
  Rill mirror (`integrations/xray_bash_onekey/repository_files/.github/test/
  test_rill_xray_agent.sh`).
- **Targeted OI PID1 qualification (P1-4)**: the copied generic 66-check
  PID1 logs were replaced with targeted OI logs produced on fresh
  systemd-PID1 containers against the frozen 0.2 tree (bundle
  `00c0ee1b770e`, SHA-verified bootstrap install): systemd PID1, bootstrap
  re-run idempotent, config invariants, DAC observation contract (read
  allowed / overwrite + history-create denied, 640/2750/socket 660), OI
  lifecycle observe->timeline->diagnose->feedback->inspect, diagnosis
  idempotency, feedback accepted then exact-replay idempotent after restart.
  Debian 12 + Ubuntu 24.04 both 24/24 PASS
  (`qualification/debian12-oi02-pid1.log`,
  `qualification/ubuntu2404-oi02-pid1.log`).

## 0.2 Phase-1 final observer convergence (this round, commits `704d367`/`98be0c4`)
- **P1-A recoverable pending transition (live-current-changed recovery)**:
  the checkpoint now persists a safe projection of the pending current
  (`schemaVersion 2`, `currentObservation`), so an in-flight O0->O1 is
  independently recoverable even when the host moved to O2 while the observer
  was down. Restart FIRST completes the pending O0->O1 from the checkpoint,
  THEN processes the new live O2, yielding the correct O0->O1->O2 chain
  instead of a bogus O0->O1 + O0->O2. See Case H/I regression tests.
- **P1-B checkpoint fail-closed**: a checkpoint that exists but cannot be
  trusted - malformed JSON, empty, wrong/unsupported schema, missing or
  ill-typed fields, invalid digests, duplicate or invalid eventTransitionIds,
  symlink, or non-regular file - raises `ObserverTransitionError` and is never
  silently discarded. Only a truly absent checkpoint returns `None` (fresh
  start). The checkpoint `eventTransitionIds` are a real recovery contract:
  re-derived ids must match exactly or recovery fails closed (no
  recompute-and-replace). Observer exits non-zero, journal/observation/
  checkpoint untouched. See Cases J-L.
- **Observer runtime integration**: `rill_xray_agent_observe.py` calls
  `recover_pending_transition` before committing any new live transition; the
  production entry path now exercises recover-then-commit, not just the unit
  helper. Checkpoint write/clear use atomic_write_json + parent-dir fsync
  (durable unlink included).
- **Fault matrix**: `tests/test_observer_transition_recovery.py` covers
  Cases A-M (baseline, single/multi-event partial commit, observation
  committed before clear, genuine repeated transition not over-deduped,
  pending recovered first when live changed, multi-event pending + live
  change, malformed/symlink/non-regular checkpoint, id mismatch, inconsistent
  projection, returnCode-only change). Same-booleans-but-returnCode-changed
  (Case M) proves a pending transition is defined by the checkpoint, never
  re-derived from a coincidentally-equal current digest.

## Production identity (canonical pin, updated this round)
- Canonical Rill production commit: `98be0c492661a83c0e13b9b6701b4657e5cbf691`
  (chore(canonical) reseal `98be0c4`; Xray workflow `RILL_CANONICAL_COMMIT` pin).
- Canonical bundle SHA-256: `c264ffa767fbf8bbd7dcb1b16172dcd3084281fb57cdfc5a041df5af9b72cfdf`

## Safety invariants (regression-tested, unchanged from v0.1.0, re-confirmed live)
- `routeAssistEnabled=false`, `boundedAutoAllowed=false`, `canApply=false`,
  `executionAllowed=false`
- Doctor never executes host commands / writes Xray config
- Runtime never writes observer history; Agent never reads host config
- raw config / secrets never persist
- Live PID1 re-confirmation: runtime process runs as `rill-xray-agent`; Runtime
  reads the observation but `Permission denied` on write/create.

## Evidence / CI
- Rill Source Gates: PASS on `feat/0.2-operational-intelligence` (PR #2).
- Xray required CI: PASS on `feat/rill-xray-agent-0.2` (PR #55) — integration,
  security-regression, and five Install jobs all green.
- Python gates: 28 isolated modules PASS (incl. `test_observer_transition_recovery`
  Cases A-M, `test_event_journal_segmenting`, `test_closed_feedback_replay`,
  `test_cli_dispatch`); canonical payload sync PASS (71 files, bundle
  `c264ffa767fb`); package sums PASS (222).
- Observer transition recovery: 19/19 PASS (`test_observer_transition_recovery`).
- Xray integration (local root run): `test_rill_xray_agent` PASS,
  `test_rill_xray_agent_healthy` 17 PASS, `operational_intelligence` PASS,
  `test_rill_xray_agent_uninstall` 17 PASS, `test_rill_uninstall_durability`
  19 PASS.
- **Targeted Docker PID1 qualification** (`qualification/*-oi02-pid1.log`):
  Debian 12 and Ubuntu 24.04 both `24/24 PASS`; DAC contract + OI lifecycle
  re-verified over real systemd sockets on both (observe->diagnose->feedback
  ->inspect->restart persistence->idempotency).
- **Re-qualification on the recoverable-transition bundle** (`98be0c4`,
  `qualification/debian12-oi-full.log`, `qualification/ubuntu2404-oi-full.log`):
  Debian 12 and Ubuntu 24.04 both `24/24 PASS` on the new bundle, including
  the observer pending-transition recovery scenarios (Case H + Case J) run
  against the installed canonical `observer_transition` implementation.

## Dynamic GitHub state (resolve at audit time)
- PR HEAD and required CI must be resolved from GitHub at audit time.
- Draft PRs: Rill `#2` (`feat/0.2-operational-intelligence` -> main),
  Xray `#55` (`feat/rill-xray-agent-0.2` -> main). Both remain Draft; 0.2 RC
  qualification (deep 20/20, five-mode, deterministic A/B, bootstrap
  re-qualification) is deferred to 0.2 RC.

## Open / blocked
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy; known
  limitation).
- 0.2 release flags: `preReleaseAllowed=false`, `sourceProcessQualified=false`,
  `stableAllowed=false` until 0.2 RC qualification.