# Current state

`1.0.0` is the frozen stable production identity on the
`release/1.0-convergence` branch (cut from `main`). All release gates pass on
exact HEAD (Docker scope). The stable 1.0 **tag** is gated on the EXTERNAL P0
(public prompt purge) — see OPEN_BLOCKERS. `0.9.0` was released as stable tag
`v0.9.0` (2026-08-12); `v0.1.0` remains RELEASED and frozen.

## Frozen 1.0 production identity (canonical)
- Rill canonical production commit (Xray `RILL_CANONICAL_COMMIT` pin; reseals
  the 1.0 bundle after the version advance).
- Bundle sha256 `434fd20fff899f363c70185932528f2be9acb88f6bf8a83d5d958522324d3b1f`.
- VERSION `1.0.0` (single version source). `candidate`/`candidateVersion`/
  `__version__` all `1.0.0`.
- Xray pinned to the reseal commit, bundle `434fd20fff89…`, bootstrap
  EXPECTED_SHA256 == bundle sha. Cross-repo verify drift-free (9 required paths).

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

## 1.0 qualification (fresh systemd-PID1 containers, Docker scope)
- Rill Source Gates PASS (exact HEAD). Xray Rill Xray Agent + Test Install
  PASS (exact HEAD).
- Debian 12 PID1 full critical PASS; Ubuntu 24.04 PID1 full critical PASS.
- Five-mode matrix (xtls_only / ws_grpc_xhttp / reality / reality_nginx / tls)
  34/0 PASS each.
- Upgrade v0.1.0 -> 1.0.0 PASS; deterministic A/B byte-identical; bootstrap
  delivery PASS; package checksum PASS.

## Governance
- Passive verification workflows: `contents: read` + `persist-credentials: false`;
  i18n workflows keep scoped write only. i18n PR fail-open closed. Xray
  release-gate umbrella added. Public history hygiene current refs/tags PASS.
- main Rulesets active: require PR + required status checks (Rill `source`;
  Xray `release-gate` + `integration`), block force push + deletion.

## External / deferred (not reported as PASS)
- Historical Rill prompt blob `00_总执行提示词.md` @ `52d7632d` still fetchable
  (HTTP 200); EXTERNAL P0 OPEN, GitHub Support purge required. Gates the stable
  1.0 tag only.
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy).