# Changelog

## 1.0.0 (2026-08-12) — prepared stable release

First stable release line. Re-sealed canonical production identity for 1.0.0
(bundle `14371ba7d078`). All release gates pass on exact HEAD (Docker
systemd-PID1 scope). Version identity 1.0.0 everywhere; cross-repo
drift-free. Stable tag gated on the EXTERNAL P0 prompt purge. See
RELEASE_NOTES.md and docs/RELEASE_GATES.md.

## 0.9.0 (2026-08-12) — stable release

First stable milestone. Re-sealed canonical production identity for 0.9.0
(bundle `1ec9166826d9`). Supersedes 0.9.0-rc.1.

## 0.9.0-rc.1 (2026-08-12) — release candidate

Feature-complete release candidate converging toward 1.0.0. From this point
only P0/P1, release engineering, qualification, compatibility, documentation,
packaging and security fixes are allowed.

### Added
- Safe Event Timeline: bounded, segmented, crash-safe journal of meaningful
  state-change events with sequence continuity, segment continuity and
  torn-tail fail-closed.
- Observer: crash-idempotent exactly-once transitions, recoverable pending
  transitions across live-state changes, process-level mutex, nested
  symlink fail-closed, checkpoint digest verification.
- Doctor v1: deterministic advisory-only diagnosis (`canApply=false`).
- Structured feedback: enum/boolean/bounded-scalar only; free-text, secret and
  config-like content rejected.
- Runtime timeline/diagnose API; CLI timeline/diagnose/feedback.
- Xray integration: lifecycle, normal/observe-only/safe-disabled, capability
  floor, diagnose/timeline, safe reinstall, config/Nginx preservation,
  rollback, uninstall/firewall/Xray update transactions, Fail2ban safety,
  offline-safe commands.
- Two-phase uninstall, bootstrap with canonical payload verification, public
  history hygiene gate.

### Fixed
- Upgrade path: re-install over a running installation now restarts every
  active Rill unit so the installed payload is the code that actually runs.
- CLI feedback dispatch: `feedback` subparser was registered but missing from
  the dispatch dict (`--json feedback` crashed with KeyError); now wired and
  regression-tested.
- DAC observation permission contract (root observer / unprivileged runtime).
- CI: passive verification workflows use minimal `contents: read` permissions
  and `persist-credentials: false`; i18n PR workflow is fail-closed; Xray
  release-gate umbrella added.

### Changed
- Version advanced to `0.9.0-rc.1` (single version source).
- Canonical production identity resealed: bundle
  `0f3fed6339255e8fa7d3b8c40b80fc51f264332f60dd95b2589e7d4c64507259`,
  Rill canonical commit `ddd83d7`, Xray `RILL_CANONICAL_COMMIT` pinned
  accordingly.

### Qualification (Docker systemd-PID1 scope)
- Rill Source Gates PASS; Xray Rill Xray Agent + Test Install PASS.
- Debian 12 PID1 66/66; Ubuntu 24.04 PID1 66/66.
- Five-mode matrix 34/0 each.
- Upgrade v0.1.0 -> 0.9.0-rc.1 34/0; deterministic A/B byte-identical;
  bootstrap delivery PASS; package checksum PASS.

### Known limitations
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy).
- Historical Rill prompt blob remains fetchable (EXTERNAL P0, GitHub Support
  purge required); does not block this prerelease.

## 0.1.0 (2026-08-10) — stable

- observe-first, local-first agent with Doctor, safe Event Timeline, structured
  feedback, bootstrap and canonical payload verification; Xray integration EOF
  for the v0.1.0 subject.