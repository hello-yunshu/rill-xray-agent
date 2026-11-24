# 05 Cross-Repo Sync Gate (Rill side)

Captured 2026-08-06 after source/process gates passed.

## Change
- Branch `fix/rc1-audit-blockers`.
- New deterministic sync tool (`scripts/sync_xray_payload.py`) and hardened drift gate
  (`verify_xray_integration.py`): source==payload byte-exact, bundle SHA == bootstrap
  EXPECTED_SHA256, bundle layout verified, version strings consistent.

## Verification
- Two consecutive syncs produce identical bundle bytes (reproducible).
- `scripts/run_all_checks.py`: all source/process gates pass (now including the drift gate).

## Note
- The bootstrap script is excluded from the bundle by design (it pins the bundle SHA).