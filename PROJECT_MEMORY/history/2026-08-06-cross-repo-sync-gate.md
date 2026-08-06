# Cross-Repository Synchronization Gate

Date: 2026-08-06

## Summary
The Rill → Xray payload → bundle → bootstrap SHA chain is now verified in CI;
any drift fails the gate.

## Chain
- Rill source: `python/rill_xray_agent/` (canonical).
- Xray payload: `integrations/xray_bash_onekey/repository_files/rill_payload/`.
- Bundle: `integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz`
  (also mirrored under `repository_files/assets/`).
- Bootstrap SHA: `EXPECTED_SHA256` in `repository_files/scripts/rill_xray_agent_bootstrap.sh`.

## Changes
- `scripts/sync_xray_payload.py` (new): deterministic sync — copies source modules
  into the payload, rebuilds the bundle (fixed mtime, sorted entries, gzip mtime=0,
  bootstrap script deliberately excluded from the archive since it pins the bundle
  SHA), and re-pins `EXPECTED_SHA256` to the fixed point.
- `scripts/verify_xray_integration.py`: now asserts source == payload (byte exact),
  bundle SHA == bootstrap `EXPECTED_SHA256`, bundle top-levels exactly
  `{rill_payload, scripts, systemd}` with full file coverage, and version consistency
  (`VERSION` == package `__version__` == payload `candidate`).

## Verification
- Two consecutive syncs produce an identical bundle (deterministic).
- `scripts/run_all_checks.py`: source/process gates pass, including the drift gate.

## Status
- Rill-side sync complete; Xray repository payload must be refreshed with
  `apply_to_repo.py` as part of the Xray-side P0 work (P0-5/6/7).