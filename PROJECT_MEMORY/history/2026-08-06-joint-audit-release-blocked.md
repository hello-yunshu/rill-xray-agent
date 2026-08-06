# Joint audit: release blocked, RC.1 not publishable

2026-08-06 joint repository review of `hello-yunshu/rill-xray-agent` and `hello-yunshu/Xray_bash_onekey` (Draft PR #54). Findings require qualification to be revoked:

- Xray CI is green but the Rill integration test is grep-only (9 lines) and does not cover lifecycle, fault injection or bundle consistency.
- P0-2: Runtime state is mutated before the audit event is appended; a crash/failure between them leaves state and audit split while the API reports failure after the state is already committed.
- P0-3: completed decisions are evicted by capacity without a permanent replay tombstone; decision identity semantics are lost.
- P0-4: RootTransaction recovery only covers transactions that already have `commit-bundle.json`; prepared/applying/verify/commit-intent/rollback crash states are unrecoverable; recommendationId is not validated.
- P0-5/P0-6/P0-7: update script candidate validation, four-party mode transition and real-path observation are missing in the host integration.
- `preReleaseAllowed` and `sourceProcessQualified` were set to true before these findings were closed; both are now revoked.
- `v0.1.0-rc.1` release is BLOCKED: no GitHub Release, no promotion, no merge of PR #54.
- Re-qualification must restart from round 1 with fresh seeds; the previous 20/20 must not be inherited.

Downgrade applied in branch `fix/rc1-audit-blockers` (Rill) and continued on `feat/rill-xray-agent` (Xray). All P0 fixes must land and merge before any `v0.1.0-rc.2` tag or Pre-release may be created. Until then the project is in Alpha audit-repair state.