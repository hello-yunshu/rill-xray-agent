# Current state

ALPHA AUDIT-REPAIR phase. Version stays 0.1.0-rc.1. Joint-audit merge blockers
for this round are code-fixed and locally green on both fix/rc1-audit-blockers
and feat/rill-xray-agent (PR #1, PR #54). Release qualification remains BLOCKED:
`preReleaseAllowed=false`, `sourceProcessQualified=false`, `stableAllowed=false`.

Closed this round (local gates): Runtime read-only root recovery, host uninstall
failure propagation, production Nginx health path, canonical de-self-reference,
public-history hygiene rewrite, pre-submit admission, fail-closed peer ACLs,
bounded closed ledger, semantic candidate self-check, pinned action SHAs.

Still open: real PID1/systemd qualification (Debian 12 / Ubuntu 24.04),
independent zero-P0 audit, fresh 20/20 randomized gates from a clean freeze, and
observation of GitHub Actions runs for the pushed branches. `v0.1.0-rc.2`
tag/Release forbidden until merged main CI is green and real-host gates pass.
Route Assist OFF, bounded auto OFF, observe-only default.