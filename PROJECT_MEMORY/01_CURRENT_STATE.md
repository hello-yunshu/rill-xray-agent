# Current state

ALPHA AUDIT-REPAIR phase. Version stays 0.1.0-rc.1. R4 Docker-only round:
Rill sealing completed (PACKAGE_SHA256SUMS / CANONICAL_MANIFEST / bundle /
bootstrap SHA byte-consistent), durable uninstall fail-closed, README socket
default corrected, Rill Source Gates green, and full Docker qualification
executed against the frozen heads. Release qualification remains BLOCKED:
`preReleaseAllowed=false`, `sourceProcessQualified=false`,
`stableAllowed=false`.

## Frozen heads
- Rill final HEAD: `0a0ab2bde9ffe2354aa3dc2db8e839fbea2e3a08`
- Xray final HEAD: `6233c3f5db303f8b0ad8e561ad152e444893b2aa`

Closed in this round (evidence under `qualification/`):
- Rill sealing (package sums 157, canonical manifest 61 files, bundle
  1a9286a5…, bootstrap fixed point), durable uninstall fault matrix 20/20,
  README runtime.sock default.
- Rill Source Gates: SUCCESS (push + PR).
- Xray canonical re-sync from final Rill SHA + `RILL_CANONICAL_COMMIT`
  pin + mandatory `verify_modes` in Test Install security-regression.
  Xray `Rill Xray Agent` gate SUCCESS; Xray `Test Install` SUCCESS.
- Docker source qualification PASS; Debian 12 PID1 39/39; Ubuntu 24.04 PID1
  39/39; five-mode matrix PASS (xtls_only / reality_nginx / ws_grpc_xhttp /
  tls / reality, fresh container per mode); fresh 20/20 PASS (seeds 1..20,
  round-01..20.log); deterministic build PASS (A==B byte-identical).

Still open: independent zero-P0 audit, RC.2/Pre-release/Stable gated,
real bare-metal/VM qualification (Docker-only policy).

PUBLIC PROMPT PURGE = EXTERNAL BLOCKER: orphan blob
52d7632ddb… / 00_总执行提示词.md still returns HTTP 200; GitHub Support is
the only official cleanup path (no filter-repo re-run).