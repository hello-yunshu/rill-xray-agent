# 2026-08-12 1.0.0 frozen production qualification (subject v2)

Qualification of the frozen 1.0.0 production subject; the Rill commit recorded
here is the canonical payload commit the Xray workflow pin points at, NOT a
running docs HEAD. All production logs in this directory
(`debian12-pid1-1.0.0.log`, `ubuntu2404-pid1-1.0.0.log`, `bootstrap-1.0.0.log`,
`upgrade-v010-1.0.0.log`, `deterministic-A/B.sha256`) were produced on fresh
systemd-PID1 containers against the frozen 1.0.0 tree. All qualification is
Docker-only.

## Frozen heads (executedAt metadata; not part of the subjectId)
- Rill qualified canonical commit `97d3c14540318268d0275d33a5649e58ff8f4c50`
  (the 1.0.0 reseal commit after the upgrade bytecode purge fix; Xray
  `RILL_CANONICAL_COMMIT` pin)
- Xray qualified delivery HEAD `2ab36c00f274f4fbe92a1c22d4d26122046d859d`
- Xray workflow pin: `RILL_CANONICAL_COMMIT: 97d3c145…` (does not chase docs HEAD)

## Qualification subject (schemaVersion 2, fully reproducible)
`qualification/QUALIFICATION_SUBJECT.json` is generated deterministically by
`scripts/build_qualification_subject.py` (`--write` with
`--rill-commit --xray-commit`, or `--check`):

- subjectId `16b3e43d0fd99162ca62a95a3bb509350c11b45869ab552e7da3ac10784c06fa`
  (sha256 of the canonically-serialized subject minus subjectId AND
  minus executedAt, so evidence-only commits do not mint new subjects)
- production tree `b1b4f59c86025f3df0252dbcf3364ded3dd64610008ddf611a985c6d50c1fab9`
  (computed by the committed generator over VERSION, bin/, config/, python/,
  schemas/, systemd/ — supported Portable Python surface only; Native Rust
  crates/Cargo.toml excluded, nativeRuntimeSupported=false)
- harness `rillHarnessSha256 793adf48c2…` / `xrayHarnessSha256 483eb97962…` /
  `qualificationHarnessSha256 4a8c749e9b…`
  (explicit committed file sets, documented deterministic fileset digest)
- bundle `14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac`
- canonical manifest `33c4c5006917a0…`
- Xray install.sh `6b77db9d210d…`, payload tree `3a76c1b0609e…`,
  systemd tree `d3e494821459…`, bootstrap `404d6f3d8e67…`
  (EXPECTED_SHA256 == bundleAssetSha256), bundle asset
  `14371ba7d078…` (== canonical bundle), delivery tree `b2a747be33cd…`

## Production qualification (all on frozen 1.0.0 subject, fresh containers)
- Full source gates: PASS (exact PR HEAD)
- Debian 12 systemd PID1 full critical: 67/67 PASS
- Ubuntu 24.04 systemd PID1 full critical: 67/67 PASS
- Five-mode matrix (fresh container per mode): `xtls_only /
  ws_grpc_xhttp / reality / reality_nginx / tls` — all PASS (34 checks each)
- Deterministic build A/B: A==B byte-identical
  (deterministic-A.sha256 vs deterministic-B.sha256)
- Bootstrap delivery (Xray bootstrap -> bundled asset): PASS, idempotent
- Upgrade v0.1.0 -> 1.0.0 -> rollback v0.1.0: PASS
  (config + state preserved, timeline continues, target version 1.0.0,
  routeAssist false, boundedAuto false, canApply false, rollback works)
- package / checksum verification: PASS

Scope note: Docker-only. None of these logs claim bare-metal coverage.

## Real-host
`REAL HOST = NOT RUN`. No VPS/VM was spun up; Docker PID1 is not real-host.

## Historical evidence (superseded, retained for provenance)
- `round-01..20.log`, `five-mode-*.log` (older 20/20 + five-mode runs), Milestone
  `debian12-pid1.log`, `ubuntu2404-pid1.log`, `bootstrap-delivery.log`,
  `upgrade-v010-rc1.log`, `upgrade-v010-0.9.0.log`, `debian12-oi*.log`,
  `ubuntu2404-oi*.log` — these reference older subjects (v0.1.0 / 0.9.0 / RC)
  and are NOT the current 1.0.0 production subject. They are retained as
  historical evidence only.

## Logs (current 1.0.0 subject)
- `debian12-pid1-1.0.0.log`, `ubuntu2404-pid1-1.0.0.log` — PID1 raw logs
- `bootstrap-1.0.0.log` — bootstrap delivery smoke
- `upgrade-v010-1.0.0.log` — v0.1.0 -> 1.0.0 -> rollback
- `deterministic-A.sha256`, `deterministic-B.sha256` — deterministic A/B
- `QUALIFICATION_SUBJECT.json` — subject pinned (generator-verified)