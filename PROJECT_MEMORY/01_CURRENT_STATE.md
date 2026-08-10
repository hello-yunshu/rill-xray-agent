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
  flags; canonical bundle resealed to `2578a1b…` and synced to Xray.

## Production identity (stable, not branch-HEAD)
- Canonical Rill production commit: `ccb3fb67a2e29c35ede41364055c3e885cd4bae8`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin; the sums-only follow-up
  `1ee01a5…` does not change canonical payload bytes).
- Canonical bundle SHA-256: `2578a1b29beafaf4dcc63d6451e89b0c7aa2b23e27376e3cd5e08ebffdae8a69`

## Safety invariants (regression-tested, unchanged from v0.1.0)
- `routeAssistEnabled=false`, `boundedAutoAllowed=false`, `canApply=false`
- Doctor never executes host commands / writes Xray config
- Runtime never writes observer history; Agent never reads host config
- raw config / secrets never persist

## Evidence / CI
- Rill Source Gates: PASS on `feat/0.2-operational-intelligence` (PR #2).
- Xray required CI: PASS on `feat/rill-xray-agent-0.2` (PR #55) — integration,
  security-regression, and five Install jobs all green.
- Python gates: 21 isolated modules PASS; canonical payload sync PASS
  (69 files, bundle `2578a1b…`); package sums PASS (209).

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