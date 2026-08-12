# Rill Xray Agent 1.0.0 Release Notes

1.0.0 prepared stable release. Code is fully qualified in the Docker
systemd-PID1 scope; the stable Git tag is blocked by an external governance
P0 (historical public prompt blob pending GitHub Support purge).

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
- Xray bundle (`14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac`)
- SHA256SUMS
- Qualification summary

## Known limitations

- Real-host qualification not run (see above).
- A historical public prompt blob remains fetchable (external P0; GitHub
  Support purge required). This is a governance item that blocks the 1.0
  stable tag and does not affect the qualified release bytes' functionality.