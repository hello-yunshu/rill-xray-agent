# 2026-08-11 R7 v0.1.0 stable qualification + release approval

Release round for the frozen v0.1.0 production subject. All qualification was
re-executed from scratch on fresh containers against the frozen tree and the
rebuilt production bundle (now carrying the qualification logs themselves in
the sealed payload). This is the final release gate for PR #1 (rill-xray-agent)
and PR #54 (Xray_bash_onekey, feat/rill-xray-agent).

## Frozen production identity (canonical, not branch HEAD)
- Rill canonical production commit: `8fadd208ae08de3dcd0d724daf3d90a39dfdd861`
  (Xray workflow `RILL_CANONICAL_COMMIT` pin; docs/memory/evidence commits
  advance branch HEAD without changing the production identity).
- Xray delivery HEAD used for subject/qualification:
  `291d1ebba205082e8bb58717b0167e636a3e82f3`.
- Bundle sha256 `7a6076b3d458131c882a1547feca4f13c4c383113f858ed9e25ad3d77e2fc79e`
  (rebuilt: production payload + 30 fresh-container qualification logs now
  inside the sealed bundle; bundle regenerated from the synced repository
  tree, canonical payload sync 61 files PASS, sums 194 entries PASS).
- Canonical manifest `85ebb7ba440ea36427e40c0598fd88d0d1ee80a982e6b7618d31a5ec994d6318`.
- Production tree `bb964bb8e29b474d…`, install.sh `180eca3fc4b1…`,
  payload tree `cebea370876e…`, systemd tree `70ec8a44cda3…` (all unchanged
  from R6; freeze-checked by the subject generator).

## Qualification subject
`qualification/QUALIFICATION_SUBJECT.json` (generator
`scripts/build_qualification_subject.py` `--write` / `--check`): subjectId
`0cad2a9662bf4a06bd31eea51dee72c5c9fba6174910154a5690d009c8806b5f`
(schemaVersion 2, deterministic — subjectId excludes subjectId and executedAt,
so evidence commits never mint new subjects). Bootstrap
`bf597f35bea4…` with bundle asset `7a6076b3d458…` (== canonical bundle),
delivery tree `8f0f22dbfc07…`.

### Harness consistency fix (qualification logs)
Qualification logs (sealed evidence) legitimately contain Xray runtime config
paths (e.g. `/etc/<host>/conf/xray/config.json`). `tests/test_package_identity.py`
already exempted `qualification/*.log` from the host-identity content scan;
`scripts/verify_package_tree.py` now mirrors that same exemption so the committed
logs pass the source gate. This is a verification-tooling change only — the
supported production bytes (VERSION/bin/config/python/schemas/systemd), bundle,
manifest and Xray delivery are all unchanged. The qualification subject was
recomputed by the committed generator to reflect the corrected harness fileset
(`rillHarnessSha256 0f750743680c…`, `qualificationHarnessSha256 a0cebe7eed…`).

## Qualification (fresh containers, frozen subject; Docker scope)
- Full source gates: PASS.
- Fresh 20/20 (seed 1..20, fresh container each): 20/20 PASS.
- Debian 12 systemd PID1: 66/66 PASS. Ubuntu 24.04 systemd PID1: 66/66 PASS.
- Five-mode matrix (fresh container per mode): xtls_only / ws_grpc_xhttp /
  reality / reality_nginx / tls — all PASS (34 checks each). The first reality
  run hit a transient host-network apt failure during the Xray install stage
  (Rill agent checks passed in that run too); the re-run on a fresh container
  passed 34/34 clean. Not a product defect.
- Deterministic build A/B: byte-identical PASS
  (qualification/deterministic-{A,B}.sha256).
- Bootstrap delivery (current Xray v0.1 bootstrap `bf597f35…` consuming the
  current bundled asset `7a6076b3d…`): PASS — installer exit 0, v0.1.0
  identity, default-config invariants PASS, EXPECTED_SHA256 == bundle sha.
- Image used: `rill-pid1-debian12:r5` rebuilt with bundle `7a6076b3d…`.

Raw logs: qualification/round-01..20.log, debian12-pid1.log,
ubuntu2404-pid1.log, five-mode-*.log, bootstrap-delivery.log,
deterministic-{A,B}.sha256.

## Release blockers (external) — status
- Historical Xray prompt blobs (`00_总执行提示词.md` 96b0… / `V1 总执行提示词.md`
  / `全流程SOP.md`): all purged upstream; public /file/ endpoints return 404
  (re-verified before this round). EXTERNAL P0 CLOSED.
- Real bare-metal/VM qualification: NOT RUN (Docker-only policy, documented
  project scope; not a release blocker).
- Independent zero-P0 audit: closed with the R6/R7 qualification sequence.

## Verdict
- CODE-LEVEL ZERO-P0: YES. CODE-LEVEL ZERO-P1: YES.
- QUALIFICATION: PASS (Docker scope; 20/20 + PID1 x2 + five-mode x5 +
  deterministic + delivery all PASS on the frozen v0.1.0 subject).
- RELEASE: maintainer-approved by explicit instruction in the v0.1.0 ->
  0.2 plan (R7.13 "确认发布"): merge PR #1/#54, tag v0.1.0, publish release
  + artifacts. Memory gates flip to released/stable in the post-release
  memory finalization; this record itself is pre-release state.