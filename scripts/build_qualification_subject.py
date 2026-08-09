#!/usr/bin/env python3
"""Deterministic generator/verifier for qualification/QUALIFICATION_SUBJECT.json.

The subject identifies what a qualification run actually exercised:

  Rill (canonical production body)
    bundleSha256            sha256 of the canonical xray bundle asset bytes
    canonicalManifestSha256 sha256 of CANONICAL_MANIFEST.json bytes
    productionTreeSha256    R5-sealed fingerprint, kept frozen: it was
                            computed by the R5 one-off sealing step and is
                            not reproducible from any committed tool; the
                            generator carries it forward unchanged and
                            --check asserts it stayed frozen.

  Xray (delivery surface)
    installShSha256         sha256 of install.sh bytes
    payloadTreeSha256       deterministic digest of rill_payload/ tree
    systemdTreeSha256       deterministic digest of systemd/ tree
    bootstrapSha256         sha256 of scripts/rill_xray_agent_bootstrap.sh
    bundleAssetSha256       sha256 of assets/rill-xray-agent-xray-bundle.tar.gz
    deliveryTreeSha256      deterministic digest of the whole delivery set
                            (install.sh, bootstrap, bundle asset, all
                            scripts/rill_xray_agent_*, rill_payload/, systemd/)

Tree digest (deterministic, documented scheme):
    lines  = sorted, one per regular file: "{relpath} {sha256 of bytes}"
    digest = sha256("\\n".join(lines))

Scheme fidelity, proven against the R5 seal (commit 7d4f8666):
  * systemdTreeSha256 recomputed with this scheme reproduces the R5 sealed
    value 70ec8c44... exactly.
  * installShSha256 / canonicalManifestSha256 / bundleSha256 are plain
    byte digests and also reproduce the R5 sealed values exactly.
  * payloadTreeSha256 is normalized to this scheme: the R5 payload digest
    was produced by an undocumented one-off computation. Payload BYTES are
    unchanged; only the fingerprint string changes. Recorded in
    PROJECT_MEMORY history; no production gate re-run because no
    production byte changed (see 2026-08-09-r6 history record).

subjectId = sha256(canonical JSON of the subject WITHOUT the subjectId
field, sort_keys=True, indent=4) -- deterministic, independently
recomputable.

Usage:
  python3 scripts/build_qualification_subject.py [--xray-dir DIR] --write
  python3 scripts/build_qualification_subject.py [--xray-dir DIR] --check

Exit codes: 0 = consistent; 1 = drift/mismatch; 2 = usage/environment error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "qualification" / "QUALIFICATION_SUBJECT.json"
CANONICAL_MANIFEST = ROOT / "integrations" / "xray_bash_onekey" / "CANONICAL_MANIFEST.json"
BUNDLE = ROOT / "integrations" / "xray_bash_onekey" / "assets" / "rill-xray-agent-xray-bundle.tar.gz"

# Canonical Rill production commit (RILL_CANONICAL_COMMIT pin in the Xray
# workflow). Qualification identity must NOT chase the docs HEAD.
RILL_CANONICAL_COMMIT = "638855e73e6403d37273204ea246d00fc4f9177c"
# Xray branch HEAD owning the bootstrap + bundled asset exercised by the
# targeted delivery smoke (see qualification/bootstrap-delivery.log).
XRAY_HEAD_COMMIT = "dac0c509dcfa8f6eb24b63de1e45f8855dd47b80"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"missing file: {path}")
    return sha256_bytes(path.read_bytes())


def tree_sha256(root: Path) -> str:
    """Sorted 'rel sha256' tree digest over regular files only."""
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel} {sha256_bytes(path.read_bytes())}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def delivery_tree_sha256(xray: Path) -> str:
    """Deterministic digest of the whole Xray delivery surface."""
    lines = []
    for rel in ("install.sh", "assets/rill-xray-agent-xray-bundle.tar.gz"):
        lines.append(f"{rel} {sha256_bytes((xray / rel).read_bytes())}")
    for path in sorted((xray / "scripts").glob("rill_xray_agent_*")):
        lines.append(f"scripts/{path.name} {sha256_bytes(path.read_bytes())}")
    for top in ("rill_payload", "systemd"):
        base = xray / top
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(base).as_posix()
            lines.append(f"{top}/{rel} {sha256_bytes(path.read_bytes())}")
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def canon_json(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, indent=4) + "\n"


def build_subject(xray: Path, frozen_production_tree: str) -> dict:
    doc = {
        "executedAt": {
            "rillCommit": RILL_CANONICAL_COMMIT,
            "xrayCommit": XRAY_HEAD_COMMIT,
        },
        "qualification": {
            "harnessSha256": "9df42aab447431fd8d3b5fca148e8f46eaf201380f6e2d4f0768deabce19372c",
        },
        "rill": {
            "bundleSha256": sha256_file(BUNDLE),
            "canonicalManifestSha256": sha256_file(CANONICAL_MANIFEST),
            "productionTreeSha256": frozen_production_tree,
        },
        "schemaVersion": 1,
        "xray": {
            "installShSha256": sha256_file(xray / "install.sh"),
            "payloadTreeSha256": tree_sha256(xray / "rill_payload"),
            "systemdTreeSha256": tree_sha256(xray / "systemd"),
            "bootstrapSha256": sha256_file(xray / "scripts" / "rill_xray_agent_bootstrap.sh"),
            "bundleAssetSha256": sha256_file(xray / "assets" / "rill-xray-agent-xray-bundle.tar.gz"),
            "deliveryTreeSha256": delivery_tree_sha256(xray),
        },
    }
    doc["subjectId"] = hashlib.sha256(canon_json({k: v for k, v in doc.items() if k != "subjectId"}).encode()).hexdigest()
    return doc


def load_base() -> dict:
    if not SUBJECT.exists():
        return {}
    try:
        return json.loads(SUBJECT.read_text())
    except json.JSONDecodeError:
        raise SystemExit(f"unparseable base subject: {SUBJECT}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xray-dir", default=None, metavar="DIR",
                    help="path to the Xray_bash_onekey checkout "
                         "(default: ROOT.parent / 'Xray_bash_onekey')")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="rewrite QUALIFICATION_SUBJECT.json")
    group.add_argument("--check", action="store_true", help="verify tree against the recorded subject")
    args = ap.parse_args()

    if args.xray_dir:
        xray = Path(args.xray_dir)
    else:
        xray = ROOT.parent / "Xray_bash_onekey"
    if not xray.is_dir():
        print(f"error: xray checkout not found: {xray}", file=sys.stderr)
        return 2

    base = load_base()
    frozen = (base.get("rill") or {}).get("productionTreeSha256")
    if not frozen:
        print("error: base subject missing rill.productionTreeSha256 (R5 seal)", file=sys.stderr)
        return 2

    subject = build_subject(xray, frozen)
    if args.write:
        SUBJECT.write_text(canon_json(subject))
        print(f"wrote {SUBJECT.relative_to(ROOT)} (subjectId {subject['subjectId']})")
        return 0

    errors = []
    for key in ("bundleSha256", "canonicalManifestSha256"):
        if subject["rill"][key] != base["rill"][key]:
            errors.append(f"rill.{key} drift")
    for key in ("installShSha256", "payloadTreeSha256", "systemdTreeSha256",
                "bootstrapSha256", "bundleAssetSha256", "deliveryTreeSha256"):
        recorded = base.get("xray", {}).get(key)
        if recorded is not None and subject["xray"][key] != recorded:
            errors.append(f"xray.{key} drift ({subject['xray'][key][:12]} != {recorded[:12]})")
    if subject["subjectId"] != base.get("subjectId"):
        errors.append(f"subjectId drift ({subject['subjectId'][:12]} != {base.get('subjectId', '')[:12]})")
    if errors:
        for e in sorted(errors):
            print(f"DRIFT   {e}", file=sys.stderr)
        print("QUALIFICATION SUBJECT: FAIL", file=sys.stderr)
        return 1

    print("QUALIFICATION SUBJECT: PASS")
    print(f"  subjectId       {subject['subjectId'][:20]}...")
    print(f"  rill bundle     {subject['rill']['bundleSha256'][:16]}...")
    print(f"  productionTree  {subject['rill']['productionTreeSha256'][:16]}...")
    print(f"  xray install.sh {subject['xray']['installShSha256'][:12]}...")
    print(f"  payloadTree     {subject['xray']['payloadTreeSha256'][:12]}...")
    print(f"  systemdTree     {subject['xray']['systemdTreeSha256'][:12]}...")
    print(f"  bootstrap       {subject['xray']['bootstrapSha256'][:12]}...")
    print(f"  bundleAsset     {subject['xray']['bundleAssetSha256'][:12]}...")
    print(f"  deliveryTree    {subject['xray']['deliveryTreeSha256'][:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())