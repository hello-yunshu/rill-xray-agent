# Current state

ALPHA AUDIT-REPAIR phase. Version stays 0.1.0-rc.1. R5 Docker-only round:
code frozen at canonical payload commit `638855e…`; full fresh qualification
re-executed on the frozen subject (20/20, PID1 Debian/Ubuntu 66/66, five-mode
34/34 each, deterministic A==B) with raw logs committed under `qualification/`.
Release qualification remains BLOCKED: `preReleaseAllowed=false`,
`sourceProcessQualified=false`, `stableAllowed=false`. MERGE-CANDIDATE only:
no merge of PR #1/#54, no RC.2, no pre-release/release, no VERSION bump.

## Frozen subject
- Rill canonical payload commit: `638855e73e6403d37273204ea246d00fc4f9177c`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin; docs/memory commits may advance
  branch HEAD without changing the qualification subject).
- Rill branch HEAD: `97e596fa638a4473365ff565c4fa8845695fb402` (evidence).
- Xray HEAD: `7dd4f866c4b36cd9f42c9406800ff401941210e7` (pin 638855e).
- QUALIFICATION_SUBJECT (qualification/QUALIFICATION_SUBJECT.json):
  subjectId `a532690a57a8b6524de8c31e3fe2681c09fe3f4d874028a4951062c86d0e7027`

## Qualification evidence (all fresh-container, frozen subject)
- Full source gates: PASS.
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20): 20/20 PASS (round-01..20.log).
- Debian 12 systemd PID1: 66/66 PASS (debian12-pid1.log).
- Ubuntu 24.04 systemd PID1: 66/66 PASS (ubuntu2404-pid1.log).
- Five-mode matrix (xtls_only / ws_grpc_xhttp / reality / reality_nginx /
  tls, fresh container each): 34/34 PASS each (five-mode-*.log).
- Deterministic build A/B: byte-identical (deterministic-{A,B}.sha256).
- package sums 191, canonical manifest 61 files + bundle bff2455c…, bootstrap
  fixed point: consistent.

## Required CI (after evidence push)
- Rill Source Gates: re-run (evidence commit).
- Xray RILL Xray Agent (pin 6388…) / Xray Test Install: re-check.

## Open / blocked
- Public prompt orphan blob `52d7632ddb… / 00_总执行提示词.md` still HTTP 200
  = EXTERNAL BLOCKER (GitHub Support only; no filter-repo re-run).
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy).
- Independent zero-P0 audit: in progress.
- Release encodes: all false. Do not auto-create RC.2 etc.