# Release gates

## v0.1.0 mandatory

- exact release-byte source gates (run_all_checks, Python tests, canonical
  manifest / package sums / package tree verification, shellcheck)
- Docker qualification (Docker-only scope; not real host):
  - fresh source/process 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container per round)
  - Debian 12 systemd PID1 suite
  - Ubuntu 24.04 systemd PID1 suite
  - five-mode matrix (xtls_only, ws_grpc_xhttp, reality, reality_nginx, tls)
  - deterministic build A/B (byte-identical canonical manifest, bundle,
    bootstrap hash, release archive)
- bootstrap delivery qualification (current Xray bootstrap -> current bundled
  asset inside a fresh container)
- Xray required CI (Rill Xray Agent + Test Install)
- independent read-only code audit (zero P0 / zero P1)
- canonical consistency (source/config/payload/bundle/manifest byte-identical,
  version identity 0.1.0 everywhere)

## Deferred / known limitations

- real bare-metal / VM qualification: **NOT RUN** (owner-approved deferral for
  v0.1.0; NOT reported as PASS)
- public prompt orphan platform purge: deferred (known governance item;
  no force history rewrite)

Deferred items are never reported as PASS.