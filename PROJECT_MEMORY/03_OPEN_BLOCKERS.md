# Open blockers (2026-08-08)

- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  this round is Docker-only by policy; real-host remains blocked.
- PUBLIC PROMPT PURGE (P0-1): the leaked `00_总执行提示词.md` blob
  (7b7a2ccf…) remains fetchable on GitHub and returns HTTP 200. It is
  reachable only by orphaned SHA — no longer reachable from any ref — but
  GitHub Support is the only official purge path and it is not automatable.
  Mitigation holds: known-blob denylist + docs-only content signatures.
- Nothing else is open for this Docker-only round.
