# Release gates

## 0.9.0-rc.1 mandatory (frozen feature-complete candidate)

- exact release-byte source gates (run_all_checks, Python tests, canonical
  manifest / package sums / package tree verification, shellcheck)
- Rill Source Gates PASS on exact HEAD; Xray Rill Xray Agent + Test Install
  PASS on exact HEAD
- Docker qualification (Docker-only scope; not real host), fresh systemd-PID1
  containers on the frozen RC canonical identity (bundle `0f3fed6339…`):
  - Debian 12 systemd PID1 suite — 66/66 PASS
  - Ubuntu 24.04 systemd PID1 suite — 66/66 PASS
  - five-mode matrix (xtls_only, ws_grpc_xhttp, reality, reality_nginx, tls)
    — 34/0 PASS each
  - deterministic build A/B (byte-identical canonical manifest, bundle,
    bootstrap hash, release archive)
  - bootstrap delivery (current Xray bootstrap -> current bundled asset)
  - upgrade v0.1.0 -> 0.9.0-rc.1 — 34/0 PASS
- Xray release-gate umbrella (fails when any qualification job fails)
- independent read-only code audit (zero P0 / zero P1)
- canonical consistency (source/config/payload/bundle/manifest byte-identical,
  version identity 0.9.0-rc.1 everywhere; cross-repo drift-free)
- safety invariants: routeAssistEnabled=false, boundedAutoAllowed=false,
  executionAllowed=false, Doctor canApply=false

## 0.9.0 / 1.0.0 (Stable) mandatory — NOT yet qualified

- Re-seal canonical for the new version (bundle identity changes with version)
- Rill Source Gates + Xray release-gate on exact HEAD
- Debian 12 / Ubuntu 24.04 PID1 (full critical at minimum)
- five-mode, upgrade, bootstrap, deterministic build re-qualified
- zero runtime P0 / P1

## Deferred / known limitations

- real bare-metal / VM qualification: **NOT RUN** (Docker-only policy; NOT
  reported as PASS)
- public prompt orphan platform purge: **EXTERNAL P0 OPEN** — the historical
  Rill blob `00_总执行提示词.md` @ `52d7632d` remains fetchable (HTTP 200);
  only GitHub Support can purge it. Required for the 1.0 stable tag only;
  does not block 0.9.0-rc.1 prerelease.

Deferred items are never reported as PASS.