# 2026-08-08 final Docker-only audit fixes

Re-verified (fresh containers):
- WAL ledger (P0-2A): idempotent identical tombstone, conflict fail-closed,
  capacity-bounded; WAL-ledger fault matrix incl. evicted-xray WAL replay.
- Migration P0-3: legacy closed mirror migrates under the WAL-ledger; every
  tombstone only removed after the ledger entry is durable; failures keep
  mirror + fail closed (MigrationError wraps ContractError/OSError family).
- Route Assist P0-4: hard OFF normalization on load persisted; mode command
  cannot resurrect it; config reports false in every mode.
- Hygiene gate: blob-hash denylist + doc-like content signatures; gate
  scans worktree, refs, tags, archives; self-flag fixed by restricting
  signatures to documentation-like blobs.
- README: rc.1 "AI execution instructions/prompt" claims removed.
- All source gates passed (non-root container, PYTHONWARNINGS=error).

Final state (post-commit 5c4ba64 / X 750ff1a):
- Live contract P0-4-live: Runtime WAL mode + routeAssistEnabled=false +
  boundedAutoAllowed=false required from the Runtime itself in every mode;
  unsafe/omitted/dead answers fail closed. rxa_get lower-cases booleans;
  CLI --socket defaults to the RUNTIME socket.
- Verified on real systemd PID1: Ubuntu 24.04 (rill-sysd-u) and Debian 12
  (rill-sysd-deb): live verify passes in observe-only / safe-disabled /
  normal; host integration, healthy 17/17, uninstall 17/17, verify_modes
  12/12, five-mode install matrix all green on both distros.
- 20/20 randomized gate seeds pass; determinism zip byte-identical (sha
  63c57ed3f719...); all source gates pass; CI green on both PRs (#1, #54).
