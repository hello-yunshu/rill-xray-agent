# Current state

`0.9.0-rc.1` is the frozen, feature-complete release candidate on the
`release/1.0-convergence` branch (cut from `main`). All qualification for this
candidate has passed (Docker scope). `preReleaseAllowed=true`,
`sourceProcessQualified=true`; `stableAllowed=false` (0.9.0 / 1.0.0 not yet
qualified). v0.1.0 remains RELEASED and frozen (tag `v0.1.0`).

## Frozen RC production identity (canonical)
- Rill canonical production commit `ddd83d7` (Xray `RILL_CANONICAL_COMMIT`
  pin; reseals the RC bundle after the install.sh upgrade-path restart fix).
- Bundle sha256 `0f3fed6339255e8fa7d3b8c40b80fc51f264332f60dd95b2589e7d4c64507259`.
- VERSION `0.9.0-rc.1` (single version source).
- Xray pinned to `ddd83d7`, bundle `0f3fed6339…`, bootstrap
  EXPECTED_SHA256 == bundle sha, install.sh upgrade restart present.
  Cross-repo verify drift-free (9 required paths).

## Core capabilities (stable assets, not to be broken)
- observe-first, local-first; `routeAssistEnabled=false`, `boundedAutoAllowed=false`,
  `executionAllowed=false`, Doctor advisory-only `canApply=false`.
- Safe Event Timeline: segmented bounded journal, sequence/segment continuity,
  torn-tail fail-closed, observer checkpoint crash idempotency, exactly-once
  transition, process-level mutex, nested symlink fail-closed.
- Doctor v1, structured feedback (enum/bool/scalar only; free-text/secret/config
  rejected), timeline/diagnose/feedback CLI + runtime API, read-only runtime, DAC.
- systemd observer (timer/path), safe-disabled, two-phase uninstall, bootstrap,
  canonical payload verification, public history hygiene gate.
- Xray: lifecycle integration, normal/observe-only/safe-disabled, capability
  floor, diagnose/timeline, safe reinstall, config/Nginx preservation, rollback,
  uninstall/firewall/Xray update transactions, Fail2ban safety, offline-safe
  commands, translation PR workflow.

## RC qualification (fresh systemd-PID1 containers, Docker scope)
- Rill Source Gates PASS (exact HEAD). Xray Rill Xray Agent + Test Install
  PASS (exact HEAD).
- Debian 12 PID1 66/66 PASS; Ubuntu 24.04 PID1 66/66 PASS.
- Five-mode matrix (xtls_only / ws_grpc_xhttp / reality / reality_nginx / tls)
  34/0 PASS each.
- Upgrade v0.1.0 -> 0.9.0-rc.1 34/0 PASS; deterministic A/B byte-identical;
  bootstrap delivery PASS; package checksum PASS.

## Governance
- Passive verification workflows: `contents: read` + `persist-credentials: false`;
  i18n workflows keep scoped write only. i18n PR fail-open closed. Xray
  release-gate umbrella added. Public history hygiene current refs/tags PASS.

## External / deferred (not reported as PASS)
- Historical Rill prompt blob `00_总执行提示词.md` @ `52d7632d` still fetchable
  (HTTP 200); EXTERNAL P0 OPEN, GitHub Support purge required.
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy).
- Next: publish 0.9.0-rc.1 (prerelease), then rc audit, 0.9.0, 1.0.0.