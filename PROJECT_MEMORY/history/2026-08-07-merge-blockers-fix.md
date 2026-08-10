# Merge Blockers Fix Round 2026-08-07

Date: 2026-08-07

## Summary
Closed the joint-audit merge blockers on both repos so PR #1 and PR #54 reach
"merge candidate" status (code gates green locally; real-host qualification
still open). No Stable, no new Release, no RC.2 created.

## Rill commits (fix/rc1-audit-blockers)
- `f18fd32` fix(runtime/ipc/state): read-only root recovery, peer ACLs +
  bounded admission, bounded closed ledger, canonical scope de-self-reference
- `ef1852a` fix(ci): self-consistent public-history hygiene + pinned action SHAs

## Xray commits (feat/rill-xray-agent)
- `de872b1` fix(rill): host uninstall failure propagation, production nginx
  health path, semantic candidate self-check (+ new tests wired into CI)
- `e246e29` sync(rill): production permission-model payload from Rill canonical

## What closed this round
- P0-1 Runtime root recovery now read-only (scan_recovery_state); Runtime never
  mutates root-owned txn data under the systemd read-only contract.
- P0-2 uninstall_all fail-closed on prepare; per-step rc accumulation; host
  post-verify gates commit vs abort (fault-injection + transaction tests added).
- P0-3 rxa_host_healthy uses nginx_main_conf production path; production-default
  contract test added.
- P0-4 canonical manifest excludes Xray-consumer .github; Xray workflow pins
  RILL_CANONICAL_COMMIT and verifies payload against the pinned manifest.
- P0-5 hygiene gate rewritten (paths + known blobs + high-confidence signatures);
  no more self-hit on governance/test content.
- P1-1 pre-submit bounded admission; P1-2 fail-closed peer ACLs; P1-3 bounded
  closed ledger + real eviction tests; P1-4 semantic candidate self-check;
  P1-6 pinned action SHAs.

## Local verification (2026-08-07)
- Rill `run_all_checks.py` PASS (13 isolated modules; canonical sync 61 files,
  bundle d55c710215fe); shellcheck PASS; hygiene PASS.
- Xray bash -n on all 4 scripts PASS; Rill agent/uninstall/healthy tests PASS;
  new uninstall-transaction (22), nginx-health-defaults (6), candidate-self-check
  (5) PASS; shell-update-metadata (12) PASS; cross-repo contract PASS.
- Xray payload verified against Rill CANONICAL_MANIFEST.json@1a7c20a: 35 files,
  bundle d55c710215fe.

## Still open (blockers)
- Real PID1/systemd qualification (Debian 12 / Ubuntu 24.04) not run.
- Independent zero-P0 audit not yet performed.
- 20/20 fresh randomized gates not re-run from round 1 after this final freeze.
- GitHub Actions runs for the pushed branches not yet observed.

## Release state
preReleaseAllowed=false, sourceProcessQualified=false, stableAllowed=false.
Not Ready for review until required CI + fresh 20/20 are green. RC.2 forbidden
until merged main CI is green and real-host gates pass.