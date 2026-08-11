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

## Production identity (canonical pin, updated this round)
- Canonical Rill production commit: `cdd0f50f2d99597958f686dc2b12030f6cc9655d`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin).
- Canonical bundle SHA-256: `fb86878a1b6b410589cd1b0efc86ef5a07550d9953228ce1f0fd4a7dd8587893`

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
- Python gates: 23 isolated modules PASS (incl. new `test_cli_dispatch`);
  canonical payload sync PASS (69 files, bundle `fb86878a1b6b…`);
  package sums PASS (213).
- Xray integration (local root run): `test_rill_xray_agent` PASS,
  `test_rill_xray_agent_healthy` 17 PASS, `operational_intelligence` PASS,
  `test_rill_xray_agent_uninstall` 17 PASS, `test_rill_uninstall_durability`
  19 PASS.
- **Targeted Docker PID1 qualification** (`qualification/*-oi02-pid1.log`):
  Debian 12 and Ubuntu 24.04 both `66/66 PASS`; DAC contract + OI lifecycle
  re-verified over real systemd sockets on both (observe->diagnose->feedback
  ->inspect->restart persistence->idempotency).

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