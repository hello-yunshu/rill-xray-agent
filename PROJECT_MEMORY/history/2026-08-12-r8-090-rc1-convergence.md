# 2026-08-12 R8 0.9.0-rc.1 convergence + release qualification

Release Engineering round for `0.9.0-rc.1` on the `release/1.0-convergence`
branch (cut from `main`). Freeze point: feature-complete, only P0/P1,
release engineering, qualification, compatibility, documentation, packaging
and security fixes allowed from here.

## Frozen RC production identity (canonical)
- Rill canonical production commit: `ddd83d7` (Xray workflow
  `RILL_CANONICAL_COMMIT` pin; reseals the RC bundle after the upgrade-path
  restart fix in `rill_xray_agent_install.sh`).
- Bundle sha256 `0f3fed6339255e8fa7d3b8c40b80fc51f264332f60dd95b2589e7d4c64507259`
  (canonical payload sync 71 files PASS, package sums PASS).
- VERSION `0.9.0-rc.1` (single version source: VERSION,
  `python/rill_xray_agent/__init__.py`, `config/default.json`).
- Xray `RILL_CANONICAL_COMMIT` pinned to `ddd83d7`, embedded bundle
  `0f3fed6339…`, bootstrap `EXPECTED_SHA256` == bundle sha, install.sh
  carries the upgrade restart block. Cross-repo verify: 9 required paths
  drift-free.

## Qualification (fresh systemd-PID1 containers, Docker scope)
- Rill Source Gates: PASS (exact HEAD `ddd83d7`).
- Xray Rill Xray Agent + Test Install: PASS (exact HEAD `4ff8bce`).
- Debian 12 systemd PID1: 66/66 PASS (re-run on frozen RC bundle).
- Ubuntu 24.04 systemd PID1: 66/66 PASS (re-run on frozen RC bundle).
- Five-mode matrix (xtls_only / ws_grpc_xhttp / reality / reality_nginx /
  tls): 34/0 PASS each.
- Upgrade v0.1.0 -> 0.9.0-rc.1: 34/0 PASS (real v0.1.0 artifact tree;
  config preserved, state migrates, upgrade-path restart verified).
- Deterministic build A/B: byte-identical (deterministic-{A,B}.sha256).
- Bootstrap delivery: PASS (EXPECTED_SHA256 == bundle sha).
- Package checksum: PASS.

## Security / governance
- Passive verification workflows now `permissions: contents: read` +
  `persist-credentials: false`; i18n workflows keep scoped write only.
- i18n PR fail-open closed (must confirm PR number/URL or fail).
- Xray release-gate umbrella added (fails when any qualification job fails).
- Public history hygiene: current refs/tags PASS.

## Release blockers (external) — status
- Historical Rill prompt blob `00_总执行提示词.md` @ `52d7632d` remains
  fetchable (HTTP 200, content readable). Orphaned from all refs; only GitHub
  Support can purge. EXTERNAL P0 stays OPEN. Mitigation holds (known-blob
  denylist + docs-only content signatures). Not writable as solved.
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy; never
  reported as PASS).
- Pre-release publish: this round requests `preReleaseAllowed=true` and
  `sourceProcessQualified=true`. `stableAllowed` stays `false` (0.9.0 / 1.0.0
  not yet qualified).

## Verdict
- CODE-LEVEL ZERO-P0: YES. CODE-LEVEL ZERO-P1: YES.
- RC qualification: PASS (Docker scope; PID1 x2 + five-mode x5 + upgrade +
  deterministic + bootstrap + checksum all PASS on the frozen 0.9.0-rc.1
  canonical identity).
- Release: 0.9.0-rc.1 prerelease publishable; 0.9.0 / 1.0.0 remain blocked.