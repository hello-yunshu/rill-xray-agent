# 2026-08-11 — OI audit fix: CLI feedback dispatch + DAC contract + PID1 qualification

## Scope
Rigorous completion of the 0.2 Operational Intelligence audit round on
`feat/0.2-operational-intelligence` (Rill) and `feat/rill-xray-agent-0.2`
(Xray), keeping the v0.1.0 security baseline intact.

## Fix
- **CLI feedback dispatch** (`python/rill_xray_agent/cli.py`): the `feedback`
  subparser was registered but missing from the dispatch dict, so
  `rill-xray-agent --json feedback …` crashed with `KeyError` over the real
  runtime socket. Added `'feedback':'feedback'` to the mapping.
- **Regression test** `tests/test_cli_dispatch.py`: drives every subcommand
  (status/health/metrics/config/snapshot/diagnose/inspect/timeline/mode/
  feedback) through `cli.main` against a fake runtime; asserts rc==0 and no
  KeyError.

## DAC observation permission contract (real systemd)
- Observation tree `/var/lib/rill-xray-agent-xray(|/status|/history)`:
  `root:rill-xray-agent`, mode `2750` (setgid).
- Observation file: `0640 root:rill-xray-agent`.
- Observe unit: `User=root Group=rill-xray-agent UMask=0027`.
- Runtime unit: `ReadOnlyPaths=/var/lib/rill-xray-agent-xray`.
- Verification: runtime process runs as `rill-xray-agent`; Runtime reads the
  observation but `Permission denied` on write and on create.

## Canonical reseal
- Bundle SHA-256 `fb86878a1b6b410589cd1b0efc86ef5a07550d9953228ce1f0fd4a7dd8587893`.
- Rill commit `cdd0f50`; Xray `RILL_CANONICAL_COMMIT` bumped to `cdd0f50`.
- Manifest/package sums regenerated (69 files / 213 sums); both `--check` PASS.

## Qualification
- Rill Source Gates: PASS (23 python modules, manifest check, package sums,
  package tree, xray integration, project memory).
- Xray integration (root): `test_rill_xray_agent`, `_healthy` 17,
  `operational_intelligence`, `_uninstall` 17, `_uninstall_durability` 19 — all PASS.
- Targeted Docker PID1: Debian 12 and Ubuntu 24.04 both `66/66 PASS`
  (`qualification/debian12-oi02-pid1.log`, `ubuntu2404-oi02-pid1.log`).
- OI lifecycle over real systemd socket on both OSes: observe->diagnose
  (HEALTHY, canApply=false)->feedback accepted->inspect completed
  (outcome=resolved)->restart persistence->diagnose idempotent->timeline
  integrity=valid.

## Safety invariants (re-confirmed live)
routeAssistEnabled=false; boundedAutoAllowed=false; canApply=false;
executionAllowed=false; Runtime does not modify Xray; Doctor does not execute
recommendations; no remote upload/API; no raw config persistence.

## State
Both branches pushed (Rill `cdd0f50`, Xray `3281a83`). Draft PRs #2 / #55 kept
Draft. 0.2 RC qualification (deep 20/20, five-mode, deterministic A/B,
bootstrap re-qual) remains deferred to 0.2 RC.