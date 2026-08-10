#!/usr/bin/env python3
"""Deterministic generator/verifier for qualification/QUALIFICATION_SUBJECT.json.

schemaVersion 2 (stable release subject). Everything that identifies "what
bytes + what test harness were qualified" is computed from committed sources
with deterministic, documented schemes. There is no opaque frozen fingerprint
and no hardcoded commit in this generator:

  executedAt            metadata only (--rill-commit / --xray-commit flags);
                        NEVER part of the subjectId hash, so evidence-only
                        commits do not mint new subjects.

  qualification
    rillHarnessSha256   fileset digest over the committed Rill harness set:
                          tests/
                          scripts/run_all_checks.py
                          scripts/run_python_tests.py
                          scripts/run_supported_release_gates.sh
                          scripts/verify_package_tree.py
                          scripts/verify_package_sums.py
                          scripts/verify_xray_integration.py
                          scripts/build_canonical_manifest.py
                          scripts/build_qualification_subject.py
    xrayHarnessSha256   fileset digest over the Xray Rill regression harness
                        set in --xray-dir:
                          .github/test/test_rill_*
                          .github/workflows/rill-xray-agent.yml
                          .github/workflows/test-install.yml
    qualificationHarnessSha256
                        sha256("rill:<rillHarnessSha256>\\nxray:<xrayHarnessSha256>")

  rill                  supported Portable Python Runtime production surface
    bundleSha256            sha256 of the canonical xray bundle asset bytes
    canonicalManifestSha256 sha256 of CANONICAL_MANIFEST.json bytes
    productionTreeSha256    deterministic tree digest over the v0.1 supported
                            production surface: VERSION, bin/, config/,
                            python/, schemas/, systemd/. Native Rust
                            (crates/, Cargo.toml) is NOT part of the supported
                            production identity (nativeRuntimeSupported=false).

  xray                  delivery surface (identity recorded separately)
    installShSha256         sha256 of install.sh bytes
    payloadTreeSha256       deterministic digest of rill_payload/ tree
    systemdTreeSha256       deterministic digest of systemd/ tree
    bootstrapSha256         sha256 of scripts/rill_xray_agent_bootstrap.sh
    bundleAssetSha256       sha256 of assets/rill-xray-agent-xray-bundle.tar.gz
    deliveryTreeSha256      deterministic digest of the whole delivery set
                            (install.sh, bootstrap, bundle asset, all
                            scripts/rill_xray_agent_*, rill_payload/, systemd/)

Tree digest (deterministic, documented scheme, unchanged from v1):
    lines  = sorted, one per regular file: "{relpath} {sha256 of bytes}"
    digest = sha256("\\n".join(lines))

fileset digest (new, same shaping as tree digest):
    lines  = sorted, one per regular file of an explicit set with paths
             relative to the passed root: "{relpath} {sha256 of bytes}"
    digest = sha256("\\n".join(lines))

subjectId = sha256(canonical JSON of the subject WITHOUT the subjectId field
and WITHOUT executedAt; sort_keys=True, indent=4) -- deterministic,
independently recomputable, stable across evidence-only commits.

Usage:
  python3 scripts/build_qualification_subject.py --xray-dir DIR \\
      --rill-commit <sha> --xray-commit <sha> --write
  python3 scripts/build_qualification_subject.py --xray-dir DIR --check

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

# v0.1 supported Portable Python Runtime production surface only. Native Rust
# (crates/, Cargo.toml) intentionally excluded: nativeRuntimeSupported=false.
RILL_PRODUCTION_SURFACE = ("VERSION", "bin", "config", "python", "schemas", "systemd")

RILL_HARNESS_FILES = (
    "tests",
    "scripts/run_all_checks.py",
    "scripts/run_python_tests.py",
    "scripts/run_supported_release_gates.sh",
    "scripts/verify_package_tree.py",
    "scripts/verify_package_sums.py",
    "scripts/verify_xray_integration.py",
    "scripts/build_canonical_manifest.py",
    "scripts/build_qualification_subject.py",
)

XRAY_HARNESS_WORKFLOWS = (
    ".github/workflows/rill-xray-agent.yml",
    ".github/workflows/test-install.yml",
)


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
        if "__pycache__" in path.relative_to(root).parts:
            continue
        rel = path.relative_to(root).as_posix()
        lines.append(f"{rel} {sha256_bytes(path.read_bytes())}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def fileset_sha256(paths: list[Path], base: Path) -> str:
    """Deterministic digest over an explicit file set; missing entries fail."""
    lines = []
    for path in sorted(paths):
        lines.append(f"{path.relative_to(base).as_posix()} {sha256_file(path)}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def collect_files(paths: list[Path], base: Path) -> list[Path]:
    """Expand the explicit file set: dirs become their regular files."""
    files: list[Path] = []
    for rel in paths:
        path = base / rel
        if path.is_dir():
            for p in path.rglob("*"):
                if p.is_file() and "__pycache__" not in p.relative_to(base).parts:
                    files.append(p)
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"missing harness path: {path}")
    return files


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


def build_subject(xray: Path, rill_commit: str, xray_commit: str) -> dict:
    rill_harness = fileset_sha256(
        collect_files(list(RILL_HARNESS_FILES), ROOT), ROOT)
    xray_harness_paths: list[Path] = [xray / rel for rel in XRAY_HARNESS_WORKFLOWS]
    xray_harness_paths += sorted((xray / ".github/test").glob("test_rill_*"))
    xray_harness = fileset_sha256(xray_harness_paths, xray)
    harness_combined = hashlib.sha256(
        f"rill:{rill_harness}\nxray:{xray_harness}\n".encode()).hexdigest()

    production_files: list[Path] = []
    for rel in RILL_PRODUCTION_SURFACE:
        path = ROOT / rel
        if path.is_dir():
            for p in path.rglob("*"):
                if p.is_file() and "__pycache__" not in p.relative_to(ROOT).parts:
                    production_files.append(p)
        elif path.is_file():
            production_files.append(path)
        else:
            raise SystemExit(f"missing production surface: {path}")
    production_tree = fileset_sha256(production_files, ROOT)

    doc = {
        "executedAt": {
            "rillCommit": rill_commit,
            "xrayCommit": xray_commit,
        },
        "qualification": {
            "harness": {
                "rillHarnessSha256": rill_harness,
                "xrayHarnessSha256": xray_harness,
                "qualificationHarnessSha256": harness_combined,
            },
        },
        "rill": {
            "bundleSha256": sha256_file(BUNDLE),
            "canonicalManifestSha256": sha256_file(CANONICAL_MANIFEST),
            "productionTreeSha256": production_tree,
        },
        "schemaVersion": 2,
        "xray": {
            "installShSha256": sha256_file(xray / "install.sh"),
            "payloadTreeSha256": tree_sha256(xray / "rill_payload"),
            "systemdTreeSha256": tree_sha256(xray / "systemd"),
            "bootstrapSha256": sha256_file(xray / "scripts" / "rill_xray_agent_bootstrap.sh"),
            "bundleAssetSha256": sha256_file(xray / "assets" / "rill-xray-agent-xray-bundle.tar.gz"),
            "deliveryTreeSha256": delivery_tree_sha256(xray),
        },
    }
    identity = {k: v for k, v in doc.items() if k not in ("subjectId", "executedAt")}
    doc["subjectId"] = hashlib.sha256(canon_json(identity).encode()).hexdigest()
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
    ap.add_argument("--rill-commit", default=None, metavar="SHA",
                    help="executedAt.rillCommit metadata (write only)")
    ap.add_argument("--xray-commit", default=None, metavar="SHA",
                    help="executedAt.xrayCommit metadata (write only)")
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

    if args.write:
        if not (args.rill_commit and args.xray_commit):
            print("error: --write requires --rill-commit and --xray-commit "
                  "(execution metadata)", file=sys.stderr)
            return 2
        subject = build_subject(xray, args.rill_commit, args.xray_commit)
        SUBJECT.write_text(canon_json(subject))
        print(f"wrote {SUBJECT.relative_to(ROOT)} (subjectId {subject['subjectId']})")
        return 0

    base = load_base()
    if base.get("schemaVersion") != 2:
        print("error: recorded subject is not schemaVersion 2", file=sys.stderr)
        return 2
    subject = build_subject(xray, "", "")

    errors = []
    for key in ("bundleSha256", "canonicalManifestSha256", "productionTreeSha256"):
        if subject["rill"][key] != base["rill"].get(key):
            errors.append(f"rill.{key} drift")
    harness = base.get("qualification", {}).get("harness", {})
    for key in ("rillHarnessSha256", "xrayHarnessSha256", "qualificationHarnessSha256"):
        if subject["qualification"]["harness"][key] != harness.get(key):
            errors.append(f"qualification.harness.{key} drift")
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
    print(f"  schemaVersion   {subject['schemaVersion']}")
    print(f"  rill bundle     {subject['rill']['bundleSha256'][:16]}...")
    print(f"  productionTree  {subject['rill']['productionTreeSha256'][:16]}...")
    print(f"  harness rill/xray/combined "
          f"{subject['qualification']['harness']['rillHarnessSha256'][:10]} / "
          f"{subject['qualification']['harness']['xrayHarnessSha256'][:10]} / "
          f"{subject['qualification']['harness']['qualificationHarnessSha256'][:10]}")
    print(f"  xray install.sh {subject['xray']['installShSha256'][:12]}...")
    print(f"  payloadTree     {subject['xray']['payloadTreeSha256'][:12]}...")
    print(f"  systemdTree     {subject['xray']['systemdTreeSha256'][:12]}...")
    print(f"  bootstrap       {subject['xray']['bootstrapSha256'][:12]}...")
    print(f"  bundleAsset     {subject['xray']['bundleAssetSha256'][:12]}...")
    print(f"  deliveryTree    {subject['xray']['deliveryTreeSha256'][:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
