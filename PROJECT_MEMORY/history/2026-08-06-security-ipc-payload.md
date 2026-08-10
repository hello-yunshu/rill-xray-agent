# Security Fix — IPC Peer Credentials, ACL, Concurrency, Payload Allowlist

Date: 2026-08-06

## Summary
Runtime IPC now extracts peer credentials (pid/uid/gid via SO_PEERCRED on Linux and
LOCAL_PEERCRED on macOS), enforces a uid ACL, caps concurrent in-flight requests,
and stores only schema-allowlisted payload metadata.

## Changes
- `python/rill_xray_agent/peer_auth.py` (new): `peer_credentials()` (Linux
  SO_PEERCRED / macOS LOCAL_PEERCRED xucred) and `AccessControl` uid allowlist.
- `python/rill_xray_agent/payload_policy.py` (new): `sanitize_payload()` — schema
  allowlist for persisted decision payloads; Xray config bodies (inbounds/outbounds/...)
  rejected; secrets/UUIDs/shortIds/tokens/vless:// redacted via the audit filter;
  raw payloads are no longer stored, only redacted metadata plus the payload digest.
- `python/rill_xray_agent/runtime_service.py`:
  - per-connection pid/uid/gid recorded in an access log (rotated at 8 MiB);
  - ACL check rejects non-allowlisted uids with `forbiddenPeer`;
  - bounded semaphore rejects excess concurrency with `serverBusy`;
  - request size limit retained (1 MiB);
  - `feedback` persists `payloadMeta` (sanitized) instead of the raw payload.
- `python/rill_xray_agent/state.py`: low-level feedback path applies the same policy.
- `tests/test_peer_credentials.py` (new): 6 tests covering credential recording, ACL
  denial, concurrency rejection, allowlist redaction/rejection, and no forbidden data
  persistence.

## Verification
- 40 unit tests pass (6 new security tests).
- `scripts/run_all_checks.py`: source/process gates pass; manifest regenerated (125).

## Status
- Security section done for Rill side. Remaining: cross-repo payload sync gate,
  Xray-side P0-5/6/7, then re-qualification and conditional deliverables.