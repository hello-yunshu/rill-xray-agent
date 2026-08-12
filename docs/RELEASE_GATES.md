# Release gates

## 1.0.0 (Stable) mandatory — code qualified, stable tag gated on EXTERNAL P0

- exact release-byte source gates (run_all_checks, Python tests, canonical
  manifest / package sums / package tree verification, shellcheck)
- Rill Source Gates PASS on exact HEAD; Xray Rill Xray Agent + Test Install
  (incl. release-gate umbrella) PASS on exact HEAD
- Docker qualification (Docker-only scope; not real host), fresh systemd-PID1
  containers on the frozen 1.0.0 canonical identity (bundle `434fd20fff89`):
  - Debian 12 systemd PID1 suite — full critical
  - Ubuntu 24.04 systemd PID1 suite — full critical
  - five-mode matrix (xtls_only, ws_grpc_xhttp, reality, reality_nginx, tls)
    — 34/0 PASS each (Xray Test Install / release-gate)
  - deterministic build A/B — byte-identical (bundle, canonical manifest,
    bootstrap hash)
  - bootstrap delivery (Xray bootstrap -> bundled asset) — PASS, idempotent
  - upgrade v0.1.0 -> 1.0.0 — config + state preserved, timeline continues,
    rollback verified
- Xray release-gate umbrella (fails when any qualification job fails)
- canonical consistency (source/config/payload/bundle/manifest byte-identical,
  version identity 1.0.0 everywhere; cross-repo drift-free)
- safety invariants: routeAssistEnabled=false, boundedAutoAllowed=false,
  executionAllowed=false, Doctor canApply=false
- zero runtime P0 / P1
- **EXTERNAL P0 OPEN** — public prompt orphan `00_总执行提示词.md` @
  `52d7632d` still fetchable (HTTP 200); only GitHub Support can purge it.
  Required for the stable 1.0 tag; does not block code/artifacts/qualification.

## 0.9.0 (Stable) — qualified, released

- Same gates as 1.0.0 on the frozen 0.9.0 identity (bundle `1ec9166826…`);
  released as stable tag `v0.9.0` (2026-08-12).
- historical; superseded by 1.0.0.

## 0.9.0-rc.1 (historical prerelease, superseded)

- Same gates on the frozen RC identity (bundle `0f3fed6339…`).
  Superseded by 0.9.0 and 1.0.0.

## Deferred / known limitations

- real bare-metal / VM qualification: **NOT RUN** (Docker-only policy; NOT
  reported as PASS)
- public prompt orphan platform purge: **EXTERNAL P0 OPEN** — the historical
  Rill blob `00_总执行提示词.md` @ `52d7632d` remains fetchable (HTTP 200);
  only GitHub Support can purge it. Required for the stable 1.0 tag only.

Deferred items are never reported as PASS.