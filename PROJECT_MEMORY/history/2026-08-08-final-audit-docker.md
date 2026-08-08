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
