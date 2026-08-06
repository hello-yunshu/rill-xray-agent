# 00 Baseline (joint audit, 2026-08-06)

Captured 2026-08-06 21:30 (UTC+8) from live GitHub state. Evidence JSON: `AUDIT_EVIDENCE/00_BASELINE.json`.

## Rill Xray Agent

- main HEAD: `4cb9117dc6eec71e3f4a18b70e20a036acc962d6` (`docs: add README (zh/en) with english entry, remove extra prompt note`)
- v0.1.0-rc.1 tag: annotated, target `52d7632ddb420e0e2d3b894e17bf96240dae32e8`
- Latest Source Gates on main: **failure** (run 31096443942)
- project_state.json still claims `preReleaseAllowed=true` / `sourceProcessQualified=true` -> MUST be downgraded

## Xray_bash_onekey

- main HEAD: `e3ba5d7474498fbb556b0cae741a629ebb3bf1cd`
- feat/rill-xray-agent HEAD: `0d512a7c33c06b0183b26a7b0f484b8d50009654`
- PR #54: OPEN / draft / mergeable / all required checks SUCCESS
- `.github/test/test_rill_xray_agent.sh` is grep-only (9 lines), no lifecycle/fault/bundle coverage

## P0 findings

| ID | Finding |
|---|---|
| P0-1 | Execution prompt removed; package manifest inconsistent; main Source Gates failing |
| P0-2 | State/audit not a single recoverable transaction (state first, audit second) |
| P0-3 | Completed eviction loses decision identity (no permanent tombstone) |
| P0-4 | RootTransaction recovery only handles commit-bundle state; recommendationId unvalidated |
| P0-5 | update.sh script replacement unvalidated (downloads over running script) |
| P0-6 | Mode switch not a config/Runtime/systemd four-party transaction |
| P0-7 | Observer reads the host mirror instead of the real Xray host configuration paths |

## Immediate downgrade (this branch)

- `preReleaseAllowed=false`, `sourceProcessQualified=false`, `stableAllowed=false`, `xrayIntegrationApplied=true`
- PR #54 remains Draft
- No new tags, no Release, no merge
