# Open blockers — 0.9.0-rc.1 convergence

- PUBLIC PROMPT PURGE (EXTERNAL P0, still open): the leaked
  `00_总执行提示词.md` blob (commit `52d7632ddb420e0e2d3b894e17bf96240dae32e8`,
  path `00_总执行提示词.md`) remains fetchable on Rill (HTTP 200, content
  readable at raw/blob URL); orphaned from all refs but only GitHub Support
  can purge it. Mitigation holds: known-blob denylist + docs-only content
  signatures + public-history hygiene gate. No filter-repo re-run. Not writable
  as solved. Required for 1.0 stable-tag only; does not block 0.9.0-rc.1.
- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  NOT RUN. This round remains Docker-only by policy; therefore not reported as
  PASS, and Stable cannot claim real-host coverage.
- 0.9.0 / 1.0.0 (Stable): BLOCKED. `stableAllowed=false`; only publish
  0.9.0-rc.1 prerelease now. Do not auto-create Stable until 0.9.0 gates pass.
- Independent zero-P0 audit: running against the frozen 0.9.0-rc.1 production
  identity (`ddd83d7` / bundle `0f3fed6339…`).
- CLOSED this round: upgrade-path restart fix (enable --now doesn't restart
  running units) resealed into the RC canonical; PID1 Debian 12 + Ubuntu 24.04
  re-run on the frozen RC bundle (66/66 each); five-mode (34/0 each); upgrade
  v0.1.0 -> 0.9.0-rc.1 (34/0); deterministic A/B; bootstrap; checksum; CI
  minimal permissions; i18n PR fail-closed; Xray release-gate umbrella.