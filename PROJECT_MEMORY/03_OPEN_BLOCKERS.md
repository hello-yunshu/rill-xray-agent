# Open blockers (2026-08-09)

- Fresh Docker qualification not yet executed against the sealed/frozen heads:
  Debian 12 PID1, Ubuntu 24.04 PID1, five-mode matrix, fresh 20/20, hard
  deterministic build. Old Docker / 20-20 PASS results were invalidated by
  the R4 code-change round and must be rerun from zero.
- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  this round is Docker-only by policy; real-host remains blocked.
- PUBLIC PROMPT PURGE (P0-1): the leaked `00_总执行提示词.md` blob
  (52d7632ddb… / 00_总执行提示词.md) remains fetchable on GitHub and returns
  HTTP 200; orphaned from all refs but only GitHub Support can purge it.
  Mitigation holds: known-blob denylist + docs-only content signatures.
- Xray consumer still pinned at the previous canonical SHA
  (5c4ba648…); backend re-sync from the final green Rill SHA is pending until
  Rill sealing commit is pushed and Rill Source Gates are green.