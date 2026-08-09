# 2026-08-09 R5/R6 Docker-only qualification (frozen subject)

Qualification of the frozen production subject; the Rill commit recorded here
is the canonical payload commit the Xray workflow pin points at, NOT a running
docs HEAD. All production logs in this directory (round-01..20, five-mode-*,
pid1) were produced on fresh containers against the frozen tree. R6 adds the
targeted bootstrap-delivery qualification below.

## Frozen heads
- Rill canonical payload commit: `638855e73e6403d37273204ea246d00fc4f9177c`
  (branch then advanced with evidence/memory commits — subject unchanged)
- Xray delivery HEAD (R6): `dac0c509dcfa8f6eb24b63de1e45f8855dd47b80`
- Xray R5 execution commit: `7dd4f866c4b36cd9f42c9406800ff401941210e7`
- Xray workflow pin: `RILL_CANONICAL_COMMIT: 638855e73e6403d37273204ea246d00fc4f9177c` (does not chase docs HEAD)

## Qualification subject
`qualification/QUALIFICATION_SUBJECT.json` is generated deterministically by
`scripts/build_qualification_subject.py` (`--write` / `--check`):

- subjectId `d96ef7f950f4905004ca096210a505e88d6174119c19a7d56f24dab0c98697d2`
  (sha256 of the canonically-serialized subject minus the subjectId key)
- bundle `bff2455c355088234deff77e371eb0d791098f490797706a08734d3d4776eba0`
- canonical manifest `f26ce16b0cbecbcef2c3159ba54b9e8817bf5f51778e8320d62e0b0184ec12d9`
- production tree `fd25bf7f7ed7e8d08a2bbdd3b5fd6fee123121a1808f067ea2f0656697de421b`
  (R5 seal, frozen — carried forward unchanged)
- harness `9df42aab447431fd8d3b5fca148e8f46eaf201380f6e2d4f0768deabce19372c`
- Xray install.sh `180eca3fc4b16f484109918ec3a410d64c8d791ae284b5df615bbaa5b2d47899`
- Xray payload tree `fead3604c241ed23acf4124fe19a98578d35859edfea263726f3cbc95fca34b6`
  (normalized to the documented deterministic tree scheme; see generator docstring)
- Xray systemd tree `70ec8a44cda35f487d0ee2fa72986af68d0bbe5804c47d5f836170802c2c4b21`
  (scheme reproduces the R5 sealed value exactly)
- Xray bootstrap `09c1cf441f57c476051b88e87a921b77aaef9fed113aa8b09caaf69bf1eb0dd4`
- Xray bundle asset `bff2455c355088234deff77e371eb0d791098f490797706a08734d3d4776eba0`
  (== canonical bundle)
- Xray delivery tree `9c3cc391061e7633f69a933a8bc7e88b6b6f96b6fe45ec8da31fdbf39ce85b34`

## Production qualification (R5 — all on frozen subject, fresh containers)
- Full source gates (manifest/sums/unittests/shellcheck): PASS
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container each): 20/20 PASS
- Debian 12 systemd PID1 raw log: 66/66 PASS
- Ubuntu 24.04 systemd PID1 raw log: 66/66 PASS
- Five-mode matrix (fresh container per mode): `xtls_only / reality /
  reality_nginx / ws_grpc_xhttp / tls` — all PASS (34 checks each)
- Deterministic build A/B: A==B byte-identical
  (deterministic-A.sha256 vs deterministic-B.sha256)

Scope note: Docker-only. The systemd PID1 runs used
`rill-pid1-debian12:r5` / `rill-pid1-ubuntu2404:r5` on Docker (arm64, Darwin
host, Docker Server 29.4.0). None of these logs claim bare-metal coverage.

## Delivery qualification (R6 — targeted bootstrap smoke)
`qualification/bootstrap-delivery.log` (raw execution output):

- current Xray bootstrap (`scripts/rill_xray_agent_bootstrap.sh`,
  sha256 `09c1cf44…`) consumed the current bundled asset
  (`assets/rill-xray-agent-xray-bundle.tar.gz`, sha256 `bff2455c…`)
- bootstrap `EXPECTED_SHA256` == actual asset SHA: PASS
- tar extraction + root-member validation (scripts/systemd/rill_payload): PASS
- real installer (from the bundle) ran staged (`DESTDIR`): exit 0
- staged artifacts present: config, runtime+agent+cli binaries, manager
  script, runtime/agent systemd units
- default config invariants: `mode=observe-only`, `routeAssistEnabled=false`,
  `boundedAutoAllowed=false`, `localOnly=true`: PASS
- container image `rill-pid1-debian12:r5`
  `sha256:29caa21f56a635d58f1a7d033842df7a5f65b64e7ee96ca45466fcd85c2a7010`
  (throwaway container; PID1 lifecycle NOT re-run — already covered by R5)
- mirror regression in Xray CI: `.github/test/test_rill_bootstrap_delivery.sh`
  (runs from `test_rill_xray_agent.sh`, i.e. inside the required workflow)

## Logs
- `round-01..20.log`     — fresh 20/20 (R5)
- `five-mode-*.log`      — five mode install+lifecycle (R5)
- `debian12-pid1.log`, `ubuntu2404-pid1.log` — PID1 raw logs (R5)
- `deterministic-A.sha256`, `deterministic-B.sha256` — deterministic A/B
- `bootstrap-delivery.log` — R6 targeted bootstrap->asset delivery smoke
- `QUALIFICATION_SUBJECT.json` — subject pinned (generator-verified)

## Xray side
- `five-mode-*.log` embed the Xray install harness (`.github/test/test_install.sh`,
  mocks + post-install assertions, redacted).
- uninstall fault-matrix logs are kept operationally (host harness), not in
  the public tree.