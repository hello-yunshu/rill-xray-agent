# 2026-08-10 v0.1.0 stable release qualification (subject v2)

Qualification of the frozen v0.1.0 production subject; the Rill commit
recorded here is the canonical payload commit the Xray workflow pin points
at, NOT a running docs HEAD. All production logs in this directory
(round-01..20, five-mode-*, pid1, bootstrap-delivery) were produced on fresh
containers against the frozen tree. All qualification is Docker-only.

## Frozen heads (executedAt metadata; not part of the subjectId)
- Rill canonical payload commit `8fadd208ae08de3dcd0d724daf3d90a39dfdd861`
  (branch then advances with evidence/memory commits — subject unchanged)
- Xray delivery HEAD `291d1ebba205082e8bb58717b0167e636a3e82f3`
- Xray workflow pin: `RILL_CANONICAL_COMMIT: 8fadd208…` (does not chase docs HEAD)

## Qualification subject (schemaVersion 2, fully reproducible)
`qualification/QUALIFICATION_SUBJECT.json` is generated deterministically by
`scripts/build_qualification_subject.py` (`--write` with
`--rill-commit --xray-commit`, or `--check`):

- subjectId `0cad2a9662bf4a06bd31eea51dee72c5c9fba6174910154a5690d009c8806b5f`
  (sha256 of the canonically-serialized subject minus subjectId AND
  minus executedAt, so evidence-only commits do not mint new subjects)
- production tree `bb964bb8e29b474d…`
  (computed by the committed generator over VERSION, bin/, config/, python/,
  schemas/, systemd/ — supported Portable Python surface only; Native Rust
  crates/Cargo.toml excluded, nativeRuntimeSupported=false)
- harness `rillHarnessSha256 0f750743680c…` / `xrayHarnessSha256 2771479f7d…` /
  `qualificationHarnessSha256 a0cebe7eed…`
  (explicit committed file sets, documented deterministic fileset digest)
- bundle `7a6076b3d458131c882a1547feca4f13c4c383113f858ed9e25ad3d77e2fc79e`
- canonical manifest `85ebb7ba440ea36427e40c0598fd88d0d1ee80a982e6b7618d31a5ec994d6318`
- Xray install.sh `180eca3fc4b1…`, payload tree `cebea370876e…`,
  systemd tree `70ec8a44cda3…`, bootstrap `bf597f35bea4…`
  (EXPECTED_SHA256 == bundleAssetSha256), bundle asset
  `7a6076b3d458…` (== canonical bundle), delivery tree `8f0f22dbfc07…`

## Production qualification (all on frozen subject, fresh containers)
- Full source gates: PASS
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container each): 20/20 PASS
- Debian 12 systemd PID1 raw log: 66/66 PASS
- Ubuntu 24.04 systemd PID1 raw log: 66/66 PASS
- Five-mode matrix (fresh container per mode): `xtls_only /
  ws_grpc_xhttp / reality / reality_nginx / tls` — all PASS (34 checks each;
  reality re-run on a fresh container after a transient host-network apt
  failure during the Xray install stage — the Rill agent stage passed in
  both runs)
- Deterministic build A/B: A==B byte-identical
  (deterministic-A.sha256 vs deterministic-B.sha256)
- Bootstrap delivery (current Xray v0.1 bootstrap `bf597f35…` consuming the
  current bundled asset `7a6076b3d…`): PASS — installer exit 0, version
  0.1.0 identity, default config safe, EXPECTED_SHA256 == bundle sha

Scope note: Docker-only. None of these logs claim bare-metal coverage.

## Real-host
`REAL HOST = NOT RUN`. No VPS/VM was spun up; Docker PID1 is not real-host.

## Logs
- `round-01..20.log` — fresh 20/20 (v0.1.0)
- `five-mode-*.log` — five mode install+lifecycle (v0.1.0)
- `debian12-pid1.log`, `ubuntu2404-pid1.log` — PID1 raw logs (v0.1.0)
- `deterministic-A.sha256`, `deterministic-B.sha256` — deterministic A/B
- `bootstrap-delivery.log` — bootstrap -> asset staged delivery smoke
- `QUALIFICATION_SUBJECT.json` — subject pinned (generator-verified)