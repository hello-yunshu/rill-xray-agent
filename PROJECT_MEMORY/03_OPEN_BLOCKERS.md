# Open blockers — 1.0.0 convergence

- PUBLIC PROMPT PURGE (EXTERNAL P0, still open): the leaked
  `00_总执行提示词.md` blob (commit `52d7632ddb420e0e2d3b894e17bf96240dae32e8`,
  path `00_总执行提示词.md`) remains fetchable on Rill (HTTP 200, content
  readable at raw/blob URL); orphaned from all refs but only GitHub Support
  can purge it. Mitigation holds: known-blob denylist + docs-only content
  signatures + public-history hygiene gate. No filter-repo re-run. Not writable
  as solved. **REQUIRED for the stable 1.0 tag only** — does not block code,
  artifacts, or qualification. All other 1.0 work is complete.
- Real-host (non-Docker) systemd / Xray / Nginx / Fail2ban qualification:
  NOT RUN. This round remains Docker-only by policy; therefore not reported as
  PASS, and Stable cannot claim real-host coverage.
- Stable 1.0 **tag**: GATED on the EXTERNAL P0 above. `stableAllowed=false`.
  Do not create the stable 1.0 tag until the prompt purge is closed.
- CLOSED this round: 0.9.0 released as stable `v0.9.0`; 1.0.0 version advance +
  canonical reseal (bundle `434fd20fff89…`); source gates PASS on exact HEAD;
  five-mode; upgrade; deterministic A/B; bootstrap; checksum; CI minimal
  permissions; i18n PR fail-closed; Xray release-gate umbrella; main Rulesets
  (Rill `source`; Xray `release-gate` + `integration`).