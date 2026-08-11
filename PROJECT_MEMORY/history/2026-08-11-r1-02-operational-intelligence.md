# 0.2 Operational Intelligence — Phase-1 implementation (R1)

Implements the first 0.2 milestone on `feat/0.2-operational-intelligence`
(branch cut from `v0.1.0`). Version identity is `0.2.0-alpha.1`; release
flags are reset to development (`preReleaseAllowed=false`,
`sourceProcessQualified=false`, `stableAllowed=false`, `routeAssistEnabled=false`,
`boundedAutoAllowed=false`). The `v0.1.0` tag is untouched.

## What was built

- **Safe Event Timeline** (`event_journal.py`, `events.py`,
  `schemas/xray-event.v1.schema.json`): bounded, crash-safe JSONL history of
  *meaningful state-change events* only (baseline, config fingerprint change,
  validation fail/recover, service up/down, unsafe path). Segment + total size
  bounds, atomic fsync'd appends, symlink rejection, corrupt-entry detection,
  safe ring-buffer rollover, read-only mode. The root observer keeps writing
  `latest: xray-observation.json` (backward compatible) and appends events.
- **Doctor v1** (`doctor.py`, `schemas/doctor-result.v1.schema.json`):
  deterministic, advisory-only diagnosis. Facts separated from inferences,
  coarse confidence bands (no pseudo-probability), fixed safe templates, 12
  ordered rules (healthy, config-changed-healthy false-positive guard,
  validation failure / service down after or before change, both-services-down,
  unsafe path, missing observation, Runtime recovery-required precedence).
  `canApply=false`, every recommendation `executionAllowed=false`.
- **Structured Feedback** (`payload_policy.sanitize_doctor_feedback`):
  enum/boolean/scalar-only allowlist; free-text, secrets and config bodies are
  rejected. Reuses the existing decision lifecycle without a fake route
  rootResult.
- **Runtime API** (`runtime_service.py`): `timeline` (READ_ONLY) and
  `diagnose` (advisory, privileged peer). Runtime reads history but never
  appends; `ReadOnlyPaths` includes the host-owned history dir.
- **CLI** (`cli.py`): `timeline --limit`, `diagnose` (human/`--json`),
  `feedback`; intents labeled semantically (sentinel/doctor/route) instead of
  hardcoded route. No security permission change.

## Safety invariants (regression-tested)

- `routeAssistEnabled=false`, `boundedAutoAllowed=false`, `canApply=false`
- Doctor never executes host commands, never writes Xray config
- Runtime never writes observer history
- raw config / secrets never persist in events or diagnosis

## Gates

- Full Rill source gates PASS (21 isolated Python modules, xray integration
  drift-free, package tree/sums, canonical manifest, project memory).
- Canonical 0.2 payload synced byte-identical into
  `Xray_bash_onekey` `feat/rill-xray-agent-0.2`.

## Not yet done (deferred to 0.2 RC)

- Deep 20/20, five-mode matrix, deterministic release A/B, bootstrap delivery
  re-qualification, Debian/Ubuntu PID1 targeted Docker.
- Xray install.sh menu (`8) Diagnose`) and non-interactive
  `--rill-agent-diagnose` / `--rill-agent-timeline` wiring.