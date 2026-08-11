# Open blockers — 0.2 Phase-1 P1 convergence audit

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
- P1 convergence items — CLOSED this round:
  - EventJournal torn-tail fail-closed + segment aggregation + closed-ledger
    feedback identity metadata + bootstrap delivery regression restore +
    targeted OI PID1 qualification (Debian 12 + Ubuntu 24.04) — closed
    previously (commits `daec959`/`9062414`/`862e778`).
  - EventJournal sequence continuity + segment continuity — closed (`e5ab62b`).
  - Observer transition crash idempotency + recoverable pending transition
    across live-current changes + checkpoint fail-closed (P1-A/P1-B) — closed
    this round (`704d367`/`98be0c4`), together with the observer recovery
    integration. Remaining for 0.2 RC: deep 20/20, five-mode, deterministic
    A/B, bootstrap re-qualification, real-host PID1.