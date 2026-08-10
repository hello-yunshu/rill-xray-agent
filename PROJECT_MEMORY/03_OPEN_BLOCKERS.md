# Open blockers — R5/R6 merge-candidate audit

- PUBLIC PROMPT PURGE (EXTERNAL P0, still open): the leaked
  `00_总执行提示词.md` blob (commit `52d7632ddb420e0e2d3b894e17bf96240dae32e8`,
  path `00_总执行提示词.md`) remains fetchable on GitHub and returns HTTP 200;
  orphaned from all refs but only GitHub Support can purge it. Mitigation
  holds: known-blob denylist + docs-only content signatures. No filter-repo
  re-run. Not writable as solved.
- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  NOT RUN. This round remains Docker-only by policy; therefore: not a Docker
  merge-candidate blocker, not qualified as real-host, and Stable cannot
  claim real-host coverage. Not written as PASS.
- RC.2 / Pre-release / Stable: BLOCKED. Do not auto-create RC.2.
- Independent zero-P0 audit: running against the frozen production identity
  at the time of this record.