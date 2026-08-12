# Rill Xray Agent 0.9.0-rc.1 Release Notes (prerelease)

This is a **release candidate** (`prerelease=true`). It is feature-complete and
fully qualified in the Docker systemd-PID1 scope, but it is not a stable
release yet. Do not treat it as `0.9.0` or `1.0.0`.

## What this is

Rill Xray Agent is a local-first, observe-first agent that safely observes a
host's Xray installation and provides a Doctor, a Safe Event Timeline, and
structured feedback, without ever enabling autonomous route changes or
execution (`routeAssistEnabled=false`, `boundedAutoAllowed=false`,
`executionAllowed=false`). It integrates with Xray_bash_onekey for lifecycle,
mode management, safe reinstall, rollback and uninstall.

## What is supported

- Portable Python Runtime (supported). Native Rust remains experimental /
  unsupported.
- Safe risk posture: observe-only by default; Doctor is advisory only
  (`canApply=false`).
- Debian 12 and Ubuntu 24.04, systemd PID 1 (qualified in Docker).
- Xray five installation modes: xtls_only, ws_grpc_xhttp, reality,
  reality_nginx, tls.

## What is NOT supported / not claimed

- Real bare-metal / VM qualification: **NOT RUN** (Docker-only policy).
- Native Rust runtime: **not a supported runtime**.
- Autonomous execution: Route Assist, bounded auto and execution remain **off**.

## Upgrade

- Upgrading from v0.1.0 is supported and qualified (config preserved, runtime
  state migrates, upgrade-path restart verified). See Upgrade Notes.

## Artifacts

- source/package archive
- Xray bundle (`0f3fed6339255e8fa7d3b8c40b80fc51f264332f60dd95b2589e7d4c64507259`)
- SHA256SUMS
- Qualification summary

## Known limitations

- Real-host qualification not run (see above).
- A historical public prompt blob remains fetchable (external P0; GitHub
  Support purge required). This is a governance item for the 1.0 stable tag
  and does not affect this prerelease's functionality.