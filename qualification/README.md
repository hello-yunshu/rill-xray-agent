# 2026-08-09 R5 Docker-only qualification (frozen subject)

Qualification of the frozen production subject; the rill commit here is the
canonical payload commit the Xray workflow pin points at, NOT a running docs
HEAD. All logs in this directory were produced on fresh containers against
the frozen tree below.

## Frozen heads
- Rill subject HEAD: `638855e73e6403d37273204ea246d00fc4f9177c`
  (canonical payload commit; branch then advanced with test-race fix
  `3f7f781` and sums refresh `f8bc334` — evidence/memory-only, subject
  unchanged)
- Xray HEAD: `7dd4f866c4b36cd9f42c9406800ff401941210e7`
- Xray workflow pin: `RILL_CANONICAL_COMMIT: 638855e73e6403d37273204ea246d00fc4f9177c` (canonical payload commit, does not chase docs HEAD)

## Qualification subject
- `QUALIFICATION_SUBJECT.json`: subjectId `a532690a57a8b6524de8c31e3fe2681c09fe3f4d874028a4951062c86d0e7027`
- bundle `bff2455c355088234deff77e371eb0d791098f490797706a08734d3d4776eba0`
- canonical manifest `f26ce16b0cbecbcef2c3159ba54b9e8817bf5f51778e8320d62e0b0184ec12d9`
- harness `9df42aab447431fd8d3b5fca148e8f46eaf201380f6e2d4f0768deabce19372c`

## Docker images
| image | digest | distro | PID1 |
|---|---|---|---|
| rill-gates-qual-r5 (source gates) | b15044eadae3450988a8926524d9ee96e7beade4f90feddf5443a120e67f6d58c | python:3.12-bookworm (Debian 12) | n/a |
| rill-pid1-debian12:r5 | 29caa21f56a635d58f1a7d033842df7a5f65b64e7ee96ca45466fcd85c2a7010 | Debian 12 (bookworm) | systemd |
| rill-pid1-ubuntu2404:r5 | 2672637f48b5c7bb131d204ff6e19c18c0049cc7d78bb55746def2f0b7139577 | Ubuntu 24.04 (noble) | systemd |

uname -m: arm64 (OrbStack, Darwin host). Docker Server 29.4.0.

## Results (all on frozen subject, fresh containers)
- Full source gates (manifest/sums/unittests/shellcheck): PASS
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container each): 20/20 PASS
- Debian 12 systemd PID1 raw log: 66/66 PASS
- Ubuntu 24.04 systemd PID1 raw log: 66/66 PASS
- Five-mode matrix (fresh container per mode): `xtls_only / reality /
  reality_nginx / ws_grpc_xhttp / tls` — all PASS (34 checks each, full
  install→agent→mode lifecycle→formal verify→two-phase uninstall→
  Xray-untouched proof)
- Deterministic build (fresh containers A & B, full sync→manifest→sums→
  bundle): A==B byte-identical (see deterministic-A.sha256 vs
  deterministic-B.sha256)

## Logs
- `round-01..20.log`   — fresh 20/20 (R5)
- `five-mode-*.log`    — five mode install+lifecycle (R5)
- `debian12-pid1.log`, `ubuntu2404-pid1.log` — PID1 raw logs (R5)
- `deterministic-A.sha256`, `deterministic-B.sha256` — deterministic A/B
- `QUALIFICATION_SUBJECT.json` — subject pinned

## Xray side
- `five-mode-*.log` embed the Xray install harness (`.github/test/test_install.sh`,
  mocks + post-install assertions, redacted).
- uninstall fault-matrix logs are kept operationally (host harness), not in
  the public tree.
