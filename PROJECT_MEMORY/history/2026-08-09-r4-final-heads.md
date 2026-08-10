# 2026-08-09 R4 final head alignment (post-qualification)

Final alignment after qualification, required for fact consistency.

## Final frozen heads (payload-canonical)
- Rill final HEAD: `8bc37a918794a9c09a722e337afbe08b3777aadf`
  (Rill Source Gates SUCCESS; qualification evidence and sealed sums in-tree)
- Xray final HEAD: `9f07dff1…` (branch feat/rill-xray-agent, PR #54)
  - CI pin refactor tail: 6233c3f -> 25e898a (badly-formed SHA) ->
    9f07dff (RILL_CANONICAL_COMMIT = 8bc37a91…). Payload bytes unchanged
    across the pin tail; canonical Xray payload verified identical
    (35 files, bundle 1a9286a5448a) against the final Rill manifest.

Both are the heads the qualification and the verified payload refer to. The
Rill memory record 2026-08-09-r4-qualification.md was written at head 8bc37a91
and remains valid; this record documents the final Xray pin chain so that the
project state is unambiguous.

## Required-CI status at frozen heads
| gate | head | status |
|---|---|---|
| Rill Source Gates | 8bc37a91 (push + PR) | SUCCESS |
| Xray Rill Xray Agent (canonical) | 9f07dff | SUCCESS |
| Xray Test Install (security-regression + 5-mode) | 9f07dff | SUCCESS |

## Evidence & gates from the qualification round
- Docker source qualification PASS; Debian 12 PID1 39/39; Ubuntu 24.04 PID1
  39/39; five-mode all PASS; fresh 20/20 PASS; deterministic build PASS;
  durable uninstall fail-closed; reachable-prompt hygiene PASS.
- PUBLIC PROMPT PURGE = EXTERNAL BLOCKER (orphan blob still HTTP 200;
  GitHub Support only fix).
- RC.2 / Pre-release / Stable BLOCKED; real bare-metal/VM NOT RUN.
- PR #1 body honours truthful wording (reachable refs clean; orphan tracked);
  PR #54 body invalidates historical 20/20 claims and states fresh
  Docker-only requalification plan.