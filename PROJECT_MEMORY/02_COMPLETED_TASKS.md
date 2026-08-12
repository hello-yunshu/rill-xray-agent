# Completed

- Portable Runtime and restricted Agent
- append-intent audit recovery
- decision identity conflict handling
- root transaction commit-bundle recovery
- safe backup and restore
- default observe-only mode
- systemd sandbox units
- complete Xray integration files and transactional apply tool
- package identity and deterministic archive checks
- Safe Event Timeline (segmented bounded journal, crash-idempotent observer
  transition, exactly-once, mutex, nested symlink fail-closed)
- Doctor v1 (advisory-only, canApply=false)
- Structured feedback (enum/boolean/scalar only)
- Logic timeline / diagnose / feedback CLI + Runtime API
- DAC read-only observer + unprivileged Runtime
- Two-phase uninstall, bootstrap, canonical payload verification
- 0.9.0-rc.1 → 0.9.0 → 1.0.0 release convergence
- 1.0.0 canonical reseal (bundle 14371ba7d078…) + cross-repo Xray sync
- 1.0.0 qualification: Rill/Xray CI PASS (exact HEAD), Debian/Ubuntu PID1,
  five-mode, upgrade v0.1.0→1.0.0, deterministic A/B, bootstrap, package sums
