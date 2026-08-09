# Current state

ALPHA AUDIT-REPAIR phase. Version stays 0.1.0-rc.1. R5 Docker-only production
qualification (20/20, PID1 Debian/Ubuntu 66/66, five-mode 34/34 each,
deterministic A==B) sealed against the canonical production commit; R6 adds the
Xray bootstrap-delivery qualification (subject extension + targeted smoke).
Release qualification remains BLOCKED: `preReleaseAllowed=false`,
`sourceProcessQualified=false`, `stableAllowed=false`. MERGE-CANDIDATE only:
no merge of PR #1/#54, no RC.2, no pre-release/release, no VERSION bump.

## Production identity (stable, not branch-HEAD)
- Canonical Rill production commit: `638855e73e6403d37273204ea246d00fc4f9177c`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin; docs/memory/evidence commits may
  advance branch HEAD without changing the production identity).
- Canonical bundle SHA-256:
  `bff2455c355088234deff77e371eb0d791098f490797706a08734d3d4776eba0`
- Canonical manifest SHA-256:
  `f26ce16b0cbecbcef2c3159ba54b9e8817bf5f51778e8320d62e0b0184ec12d9`
- Production tree SHA-256:
  `fd25bf7f7ed7e8d08a2bbdd3b5fd6fee123121a1808f067ea2f0656697de421b`

## Qualification subject
`qualification/QUALIFICATION_SUBJECT.json` (generator:
`scripts/build_qualification_subject.py`, `--write` / `--check`):
- subjectId `d96ef7f950f4905004ca096210a505e88d6174119c19a7d56f24dab0c98697d2`
- Xray install.sh `180eca3fc4b1…`, payload tree `fead3604c241…`,
  systemd tree `70ec8a44cda3…`
- Xray bootstrap `09c1cf441f57…`, bundle asset
  `bff2455c3550…` (== canonical bundle), delivery tree `9c3cc391061e…`

## Evidence (fresh-container)
- Production gates: full source gates PASS; fresh 20/20 PASS; Debian 12 PID1
  66/66; Ubuntu 24.04 PID1 66/66; five-mode 34/34 each; deterministic A==B.
- Delivery (R6): targeted current-Xray bootstrap -> current bundled asset
  Docker smoke PASS — raw log `qualification/bootstrap-delivery.log`.
  Mirror regression `.github/test/test_rill_bootstrap_delivery.sh` runs inside
  the Xray required `test_rill_xray_agent.sh` suite.

## Dynamic GitHub state (resolve at audit time)
- PR HEAD and required CI conclusions must be resolved from GitHub at audit
  time. This document is not authoritative for the current remote HEAD.
- Rill Source Gates: re-run after this push (evidence commit).
- Xray Rill Xray Agent (pin 638855e…) / Test Install: re-check.

## Open / blocked
- Public prompt orphan blob `52d7632ddb… / 00_总执行提示词.md` still HTTP 200
  = EXTERNAL BLOCKER (GitHub Support only; no filter-repo re-run).
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy). Not a
  Docker merge-candidate blocker; does not claim real-host coverage.
- Independent zero-P0 audit: in progress.
- Release encodes: all false. Do not auto-create RC.2 etc.