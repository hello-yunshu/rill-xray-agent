# Open blockers (2026-08-09, after R4 qualification)

- PUBLIC PROMPT PURGE (P0-1): the leaked `00_总执行提示词.md` blob
  (52d7632ddb… / 00_总执行提示词.md) remains fetchable on GitHub and returns
  HTTP 200; orphaned from all refs but only GitHub Support can purge it.
  Mitigation holds: known-blob denylist + docs-only content signatures.
  PR #1 documents this honestly; no filter-repo re-run.
- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  this round is Docker-only by policy; real bare-metal/VM remains blocked.
- RC.2 / Pre-release / Stable: BLOCKED. Do not auto-create RC.2.
- Independent zero-P0 audit running against frozen head at time of this record.