# 04 Security Fix (Rill side)

Captured 2026-08-06 after source/process gates passed.

## Change
- Branch `fix/rc1-audit-blockers`.
- IPC: peer credentials (pid/uid/gid) via SO_PEERCRED (Linux) / LOCAL_PEERCRED
  (macOS xucred); uid ACL (`forbiddenPeer`); bounded concurrency (`serverBusy`);
  1 MiB request limit; access log with rotation.
- Data protection: schema allowlist via `sanitize_payload()`; Xray config bodies
  rejected; secrets/UUIDs/shortIds/tokens/vless:// redacted; raw payloads never
  persisted (metadata + digest only).

## Verification
- 40 unit tests pass (6 new security tests).
- `scripts/run_all_checks.py`: source/process gates pass.