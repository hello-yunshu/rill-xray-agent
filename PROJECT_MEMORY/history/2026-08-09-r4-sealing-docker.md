# 2026-08-09 R4 sealing + Docker-only qualification state

Sealed and re-qualified after the WAL-mutation-fence / RuntimeDirectory round
(commit 6d4c5b9 / 48c409b). All work Docker-only; no host system state touched.

## Sealing (Rill authoritative source)

- `PACKAGE_SHA256SUMS` fully regenerated (156 entries, `expected == actual`,
  no missing/extra/stale hash; `scripts/verify_package_sums.py` PASS).
- Canonical payload re-synced: `errors.py`, `operation.py`, `state.py`
  mirrors updated from source; they are byte-identical.
- `CANONICAL_MANIFEST.json` rebuilt (61 files), bundle rebuilt deterministically
  (mtime=0, GNU tar, gzip mtime=0, fixed-point bootstrap EXPECTED_SHA256).
- Bundle SHA-256 = 1a9286a5448a45b7457dbcd696e85e7c068ee4a58f3116b23b85e0755e76a529;
  both bundle copies (assets/, repository_files/assets/) identical; bootstrap
  `EXPECTED_SHA256` equals `bundleSha256`; `build_canonical_manifest.py --check`
  PASS.

## Durable uninstall (fail-closed, R4-18..21)
- `rxa_uninstall_mark` fail-closed: any marker-write failure returns non-zero
  (no more `|| return 0` / `|| true` swallowing); a non-durable committed
  marker blocks the purge; a non-durable aborted marker cannot turn a host
  failure into success.
- Host `rxa_uninstall_prepare`: `install -d` failure or intent printf failure
  now returns non-zero -> host uninstall MUST NOT begin (prepare intent write
  is no longer swallowed).
- Host `rxa_uninstall_commit`: commit-marker write failure returns non-zero
  and diagnostics are NOT purged.
- `rxa_uninstall_abort`: abort marker write failure never converts the
  original host failure to success.
- Fault matrix (fresh Docker FS, 20/20 PASS): prepare success, readonly
  parent, write failure, rename failure, commit-marker failure, abort-marker
  failure, stale intent overwrite, restart/readback.

## README / hygiene
- README.md + README_EN.md: CLI default socket corrected to
  `/run/rill-xray-agent/runtime.sock` (was agent.sock).
- Outdated "one AI execution prompt" claims removed from public README text.

## Gate status (Docker, python:3.12-bookworm, non-root)
- `scripts/run_all_checks.py` (seed 1) PASS; explicit WAL/ledger/mode/runtime/
  ACL/peer unit list PASS (PYTHONWARNINGS=error::ResourceWarning).
- `verify_public_history_hygiene.py` PASS; shellcheck (SC1091 excluded) PASS
  on repository_files scripts.
- Old Docker/20-20/qualification results are INVALIDATED by the code change:
  fresh qualification is mandatory after the final heads freeze.

## Open / external
- Orphan prompt blob (52d7632ddb420e0e2d3b894e17bf96240dae32e8 /
  00_总执行提示词.md) still returns HTTP 200 -> PUBLIC PROMPT PURGE =
  EXTERNAL BLOCKER (needs GitHub Support).
- Real bare-metal/VM PID1 qualification remains blocked (Docker-only policy).