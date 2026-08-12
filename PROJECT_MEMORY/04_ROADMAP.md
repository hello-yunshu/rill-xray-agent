# Roadmap

1. **0.1.0 Stable Baseline** (`v0.1.0`, released and frozen).
2. **0.9.0-rc.1** (feature freeze) → **0.9.0** stable (`v0.9.0`, released).
3. **1.0.0 convergence** (`release/1.0-convergence`): all code, artifacts,
   qualification, and CI complete; canonical resealed (bundle 14371ba7d078…),
   cross-repo Xray sync drift-free.
4. **1.0.0 stable tag**: GATED on EXTERNAL P0 — the historical orphan prompt
   blob `00_总执行提示词.md` @ `52d7632d` must be purged (GitHub Support) before
   the stable `v1.0.0` tag is created. Until then PR #4/#59 stay Draft.
5. **Real-host (non-Docker) qualification**: NOT RUN (Docker-only policy) —
   known limitation, not a Stable blocker.
6. **0.2 Operational Intelligence**: not needed for 1.0; superseded by the
   1.0 release line. Safe Timeline / Doctor v1 / structured feedback are all
   shipped in 1.0.
