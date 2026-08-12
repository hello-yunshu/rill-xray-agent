# Release gates

## 0.9.0 (Stable) mandatory — qualified

- exact release-byte source gates (run_all_checks, Python tests, canonical
  manifest / package sums / package tree verification, shellcheck)
- Rill Source Gates PASS on exact HEAD; Xray Rill Xray Agent + Test Install
  (incl. release-gate umbrella) PASS on exact HEAD
- Docker qualification (Docker-only scope; not real host), fresh systemd-PID1
  containers on the frozen 0.9.0 canonical identity (bundle `1ec9166826…`):
  - Debian 12 systemd PID1 suite — 66/66 PASS
  - Ubuntu 24.04 systemd PID1 suite — 66/66 PASS
  - five-mode matrix (xtls_only, ws_grpc_xhttp, reality, reality_nginx, tls)
    — 34/0 PASS each (Xray Test Install / release-gate)
  - deterministic build A/B — byte-identical (bundle, canonical manifest,
    bootstrap hash)
  - bootstrap delivery (Xray bootstrap -> bundled asset) — PASS, idempotent
  - upgrade v0.1.0 -> 0.9.0 — 34/0 PASS (config + state preserved, timeline
    continues, rollback verified)
- Xray release-gate umbrella (fails when any qualification job fails)
- canonical consistency (source/config/payload/bundle/manifest byte-identical,
  version identity 0.9.0 everywhere; cross-repo drift-free)
- safety invariants: routeAssistEnabled=false, boundedAutoAllowed=false,
  executionAllowed=false, Doctor canApply=false
- zero runtime P0 / P1

## 0.9.0-rc.1 (historical prerelease, superseded by 0.9.0)

- Same gates as 0.9.0 on the frozen RC identity (bundle `0f3fed6339…`);
  preReleaseAllowed=true, sourceProcessQualified=true, stableAllowed=false.
  Superseded by the 0.9.0 stable release.

## 1.0.0 (Stable) mandatory — NOT yet qualified

- Re-seal canonical for version 1.0.0 (bundle identity changes with version)
- Rill Source Gates + Xray release-gate on exact HEAD
- Debian 12 / Ubuntu 24.04 PID1 (full critical at minimum)
- five-mode, upgrade, bootstrap, deterministic build re-qualified
- zero runtime P0 / P1
- public prompt orphan platform purge (EXTERNAL P0) required for the stable
  1.0 tag only

## Deferred / known limitations

- real bare-metal / VM qualification: **NOT RUN** (Docker-only policy; NOT
  reported as PASS)
- public prompt orphan platform purge: **EXTERNAL P0 OPEN** — the historical
  Rill blob `00_总执行提示词.md` @ `52d7632d` remains fetchable (HTTP 200);
  only GitHub Support can purge it. Required for the 1.0 stable tag only;
  does not block 0.9.0.

Deferred items are never reported as PASS.