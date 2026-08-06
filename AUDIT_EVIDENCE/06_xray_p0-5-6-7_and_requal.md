# 06 Xray-Side P0-5/6/7 Fixes and Re-qualification (Rill side)

Captured 2026-08-06.

## Change
- Branch `fix/rc1-audit-blockers`.
- P0-5: `tools/apply_to_repo.py` rewrites every `download_script_file`
  call in the host `install.sh` to download to `install.sh.rxa-candidate.$$`,
  validate via `rxa_candidate_guard` (bash -n, schema, menu, CLI and
  hook anchors), then atomically `mv` over the running script; any
  failure keeps the old version. Covers `update_sh()` and the alternate
  self-update path. The guard is embedded in the integration block so it
  works even without installed agent files; re-apply canonicalizes the
  block.
- P0-6: `rxa_apply_mode` is now a four-party transaction (Runtime WAL,
  systemd units, observation snapshot, persisted config) with rollback on
  any failure. Backed by `tests/test_mode_transaction.py`.
- P0-7: observer reads the real host Xray layout via `RILL_XRAY_HOST_ROOT`
  (observe.py default, observe.service Environment, observe.path
  PathChanged); Rill core/payload stay identity-clean. Backed by
  `tests/test_observer_real_paths.py`. Identity boundary scoped to
  `integrations/xray_bash_onekey/` in `verify_package_tree.py` and
  `test_package_identity.py`.

## Verification
- New tests: test_update_guard (10), test_mode_transaction (6),
  test_observer_real_paths (5) — all green.
- `run_all_checks.py` 20 rounds (seeds 0..19, parallel) all pass.
- Fresh clone of the remote branch gated: all source/process gates pass
  (head 2a85aa1).
- Xray host side (commit fc08e30, PR #54): `.github/test/test_rill_xray_agent.sh`
  passes, post-integration `verify_repo.py` passes, repo regression suites
  pass locally (update metadata 12/12, offline commands 39/39, version
  loading 6/6). The `Rill Xray Agent` PR check is green; push-triggered
  reruns were delayed by GitHub Actions "Service Unavailable" action
  download outages, not by code.
- Bundle SHA re-pinned to 1d238f19...; PACKAGE_SHA256SUMS (137 entries)
  and PROJECT_MEMORY chain (10 records) regenerated.

## Delivery status
- RC.2 not tagged, not released. Deliverable is the audited repair state
  on `fix/rc1-audit-blockers` + Xray `feat/rill-xray-agent` (PR #54).