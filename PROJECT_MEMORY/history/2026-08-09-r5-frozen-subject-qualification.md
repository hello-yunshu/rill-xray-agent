# 2026-08-09 R5 Docker-only qualification (frozen subject)

Qualification of the frozen production subject on fresh containers. Evidence:
`qualification/` (round-01..20.log, five-mode-*.log, debian12/ubuntu2404-pid1
logs, deterministic-{A,B}.sha256, QUALIFICATION_SUBJECT.json, README.md).

## Frozen subject
- Rill canonical payload commit: `638855e73e6403d37273204ea246d00fc4f9177c`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin).
- Branch advanced afterwards (evidence only): test-race fix `3f7f781`,
  sums refresh `f8bc334`, qualification evidence commit `97e596f`.
  Subject unchanged.
- Xray HEAD: `7dd4f866c4b36cd9f42c9406800ff401941210e7`.
- subjectId `a532690a57a8b6524de8c31e3fe2681c09fe3f4d874028a4951062c86d0e7027`;
- bundle `bff2455c355088234deff77e371eb0d791098f490797706a08734d3d4776eba0`
- canonical manifest `f26ce16b0cbecbcef2c3159ba54b9e8817bf5f51778e8320d62e0b0184ec12d9`
- harness `9df42aab447431fd8d3b5fca148e8f46eaf201380f6e2d4f0768deabce19372c`

## Outcomes (fresh containers, frozen subject)
- Full source gates (run_all_checks + shellcheck + ResourceWarning unittest
  trio): PASS.
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20): 20/20 PASS (round-01..20.log).
- Debian 12 systemd PID1 (ps -p 1 = systemd; mode lifecycle observe-only ->
  safe-disabled -> observe-only -> normal; sockets; RuntimeDirectory
  retention; formal verify; agent restart recovery; two-phase durable
  uninstall with committed-before-purge watcher): 66/66 PASS.
- Ubuntu 24.04 systemd PID1: 66/66 PASS.
- Five-mode matrix (fresh privileged container per mode; real Xray install
  via Xray `.github/test/test_install.sh` with CI mocks; Rill agent install
  -> startup -> lifecycle -> formal verify -> two-phase uninstall ->
  Xray-untouched check): xtls_only / ws_grpc_xhttp / reality /
  reality_nginx / tls all PASS (34/34 each).
- Deterministic build (two fresh containers, full sync->manifest->sums->
  bundle): A==B byte-identical (5 artifacts; bundle
  bff2455c3550… consistent with frozen subject).

## CI / push state
- Rill Source Gates: re-run pending after this push (new qualification
  evidence commit).
- Xray Rill Xray Agent (pin 638855e): pinned subject unchanged; SUCCESS
  previously, re-check after push.
- Xray Test Install: SUCCESS previously; re-check.

## Prompt blockers
- EXTERNAL BLOCKER unchanged: orphan blob
  `52d7632ddb420e0e2d3b894e17bf96240dae32e8 / 00_总执行提示词.md` HTTP 200.
- No PRE-RELEASE / RELEASE / VERSION bump; merge-candidate only. Do not
  create RC.2.

## Remaining
- Push both repos; re-check required CI; final verify; final report.
