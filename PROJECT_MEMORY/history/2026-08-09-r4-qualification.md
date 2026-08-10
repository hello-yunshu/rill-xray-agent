# 2026-08-09 R4 Docker qualification (final frozen heads)

Qualification evidence: `qualification/` (logs + deterministic sha256 pairs).

## Frozen heads
- Rill final HEAD: `0a0ab2bde9ffe2354aa3dc2db8e839fbea2e3a08`
- Xray final HEAD: `6233c3f5db303f8b0ad8e561ad152e444893b2aa`

## Outcomes
- Docker source qualification (fresh non-root container, frozen Rill tree,
  `run_all_checks` + schema/package-tree/sums/manifest/project-memory/xray-
  integration/public-hygiene + shellcheck + explicit ResourceWarning unittest
  list): PASS.
- Debian 12 systemd PID1 (`ps -p 1 -o comm=` = systemd; mode lifecycle
  observe-only -> safe-disabled -> observe-only -> normal -> safe-disabled ->
  observe-only with host config / Runtime WAL mode + routeAssist=false +
  boundedAuto=false / unit states / observation / runtime.sock / agent.sock
  stale-REFUSE semantics / formal verify per step; RuntimeDirectory retention:
  safe-disabled keeps /run/rill-xray-agent + connectable runtime.sock; agent
  restart on observe-only recover; durable uninstall prepared+abort markers):
  39/39 PASS.
- Ubuntu 24.04 systemd PID1: 39/39 PASS (same suite).
- Five-mode matrix (fresh privileged container per mode, frozen Xray install
  script: install -> Rill bundle install -> agent startup -> safe-disabled ->
  observe-only -> normal -> formal verify -> standalone two-phase uninstall ->
  cleanup verify -> destroy): xtls_only / reality_nginx / ws_grpc_xhttp / tls /
  reality all PASS.
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container per round, frozen
  source, full gate order incl. WAL fence + explicit unittest list):
  20/20 PASS (round-01..20.log).
- Deterministic build: two fresh containers, full sync->manifest->sums
  pipeline; bundle / CANONICAL_MANIFEST / PACKAGE_SHA256SUMS / bootstrap /
  uninstall byte-identical (deterministic-A.sha256 == deterministic-B.sha256).
- Required CI on final branches:
  - Rill Source Gates: SUCCESS (0a0ab2b, push + PR)
  - Xray `Rill Xray Agent` canonical gate: SUCCESS (6233c3f with pin
    0a0ab2b)
  - Xray `Test Install` (security-regression incl. verify_modes mandatory +
    5 install matrix): SUCCESS

## Prompt blockers
- PUBLIC PROMPT PURGE = EXTERNAL BLOCKER (unchanged): orphan blob
  `52d7632ddb420e0e2d3b894e17bf96240dae32e8 / 00_总执行提示词.md` still returns
  HTTP 200 from raw.githubusercontent.com; GitHub Support is the only cleanup
  path. filter-repo NOT re-run. PR #1 body states this honestly.
- `v0.1.0-rc.1` tag re-pointed at the clean sealed head; tag README no longer
  claims "one AI execution prompt" (checked: no such string at tag/HEAD).
- Real bare-metal/VM PID1 qualification: NOT RUN (Docker-only policy).

## Remaining
- Independent zero-P0 audit (in progress at time of writing).
- RC.2/Pre-release/Stable: BLOCKED. Do not auto-create RC.2.