# Current state

ALPHA AUDIT-REPAIR phase. Version stays 0.1.0-rc.1. R4 Docker-only round:
Rill sealing completed (PACKAGE_SHA256SUMS / CANONICAL_MANIFEST / bundle /
bootstrap SHA all regenerated and byte-consistent), durable uninstall made
fail-closed, README socket default corrected. Release qualification remains
BLOCKED: `preReleaseAllowed=false`, `sourceProcessQualified=false`,
`stableAllowed=false`.

Closed this round (local Docker gates): Rill sealing (package sums 156/156,
canonical manifest 61 files, bundle 1a9286a5…, bootstrap fixed point), durable
uninstall fault matrix 20/20 (readonly parent / write / rename / commit-marker
/ abort-marker / stale intent / restart-readback), README runtime.sock default,
Source Gates green in fresh python:3.12-bookworm container.

Still open: fresh Docker qualification after the final heads freeze (Debian 12 /
Ubuntu 24.04 PID1, five-mode matrix, fresh 20/20, deterministic build),
independent zero-P0 audit, Xray canonical re-sync + required CI, and the
external prompt purge blocker. `v0.1.0-rc.2` tag/Release forbidden until merged
main CI is green and real-host gates pass. Route Assist OFF, bounded auto OFF,
observe-only default.

PUBLIC PROMPT PURGE = EXTERNAL BLOCKER: orphan blob
52d7632ddb420e0e2d3b894e17bf96240dae32e8 / 00_总执行提示词.md still returns
HTTP 200; GitHub Support purge is the only official path (no filter-repo
re-run).
