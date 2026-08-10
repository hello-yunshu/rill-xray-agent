# Current state

FINAL RELEASE ROUND for v0.1.0 (R7). All release qualification re-executed
from scratch on fresh containers against the frozen subject and PASSED:
source gates, fresh 20/20, Debian 12 + Ubuntu 24.04 PID1 (66/66 each),
five-mode x5 (34/34 each; reality re-run clean on a fresh container after a
transient host-network apt failure), deterministic A==B, bootstrap delivery.
Public prompt blobs purged upstream (external P0 CLOSED). Memory gates remain
pre-release (release sequence executes after merge per maintainer approval).

## Production identity (stable, not branch-HEAD)
- Canonical Rill production commit: `8fadd208ae08de3dcd0d724daf3d90a39dfdd861`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin; docs/memory/evidence commits may
  advance branch HEAD without changing the production identity).
- Canonical bundle SHA-256:
  `7a6076b3d458131c882a1547feca4f13c4c383113f858ed9e25ad3d77e2fc79e`
- Canonical manifest SHA-256:
  `85ebb7ba440ea36427e40c0598fd88d0d1ee80a982e6b7618d31a5ec994d6318`
- Production tree SHA-256:
  `bb964bb8e29b474d…` (unchanged since R6; freeze-checked)

## Qualification subject
`qualification/QUALIFICATION_SUBJECT.json` (generator:
`scripts/build_qualification_subject.py`, `--write` / `--check`):
- subjectId `0cad2a9662bf4a06bd31eea51dee72c5c9fba6174910154a5690d009c8806b5f`
  (schemaVersion 2; excludes subjectId/executedAt, so evidence commits do not
  mint new subjects)
- Xray install.sh `180eca3fc4b1…`, payload tree `cebea370876e…`,
  systemd tree `70ec8a44cda3…`, bootstrap `bf597f35bea4…`, bundle asset
  `7a6076b3d458…` (== canonical bundle), delivery tree `8f0f22dbfc07…`

## Evidence (fresh-container)
- Production gates: full source gates PASS; fresh 20/20 PASS; Debian 12 PID1
  66/66; Ubuntu 24.04 PID1 66/66; five-mode 34/34 x5; deterministic A==B.
- Delivery: current-Xray bootstrap -> current bundled asset Docker smoke PASS
  (`qualification/bootstrap-delivery.log`); mirror regression runs inside the
  Xray required `test_rill_xray_agent.sh` suite.
- Qualification logs are committed as repo evidence and pinned in
  `PACKAGE_SHA256SUMS` (194 sums PASS, canonical payload sync 61 files PASS);
  they are NOT packed inside the shipped bundle (bundle = 33 payload files).

## Dynamic GitHub state (resolve at audit time)
- PR HEAD and required CI conclusions must be resolved from GitHub at audit
  time. This document is not authoritative for the current remote HEAD.
- Rill Source Gates: re-run after this push (evidence commit).
- Xray Rill Xray Agent (pin 8fadd208…) / Test Install: re-check.

## Open / blocked
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy; documented
  scope, not a release blocker).
- Release encodes: preReleaseAllowed=false, stableAllowed=false — flipped to
  released state by the post-merge memory finalization (maintainer-approved
  release sequence: merge -> tag v0.1.0 -> release -> artifacts).
- No blockers remain for the v0.1.0 stable release at code level.